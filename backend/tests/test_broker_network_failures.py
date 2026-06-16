import pytest
import requests
from app.bot.toss_api import TossClient
from app.core.exceptions import StockAutoException

def test_toss_api_timeout_raises_stockauto_exception(mocker):
    """
    [테스트 목적]
    토스증권 등 외부 API 호출 시 응답이 오랫동안 지연(Timeout)될 경우,
    시스템이 멈추지 않고 적절한 StockAutoException으로 감싸서 예외를 던지는지 검증합니다.
    """
    mocker.patch("app.bot.toss_api.decrypt_credential", return_value="dummy")
    db_cred = mocker.Mock(user_id=1, app_key="k", app_secret="s", account_no="n")
    api = TossClient(db_credential=db_cred, trade_mode="REAL")
    
    # get_account_balance가 호출할 get_access_token과 get_account_sequence를 Mock 처리
    mocker.patch.object(api, "get_access_token", return_value="dummy_token")
    mocker.patch.object(api, "get_account_sequence", return_value="dummy_seq")
    
    # Mock requests.get to raise a Timeout during assets fetch
    mocker.patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timed out"))
    
    # 자산 조회 시 예외가 StockAutoException으로 감싸져서 나오는지 확인
    with pytest.raises(StockAutoException) as excinfo:
        api.get_account_balance(exchange_rate=1400.0)
        
    assert excinfo.value.status_code == 502

def test_toss_api_503_service_unavailable(mocker):
    """
    [테스트 목적]
    외부 API 서버가 점검 중이거나 다운되어 HTTP 503(Service Unavailable) 에러를 반환할 때,
    잘못된 JSON 파싱 등으로 크래시나지 않고 StockAutoException을 통해 안전하게 처리되는지 검증합니다.
    """
    mocker.patch("app.bot.toss_api.decrypt_credential", return_value="dummy")
    db_cred = mocker.Mock(user_id=1, app_key="k", app_secret="s", account_no="n")
    api = TossClient(db_credential=db_cred, trade_mode="REAL")
    
    mocker.patch.object(api, "get_access_token", return_value="dummy_token")
    mocker.patch.object(api, "get_account_sequence", return_value="dummy_seq")
    
    # Create a fake 503 response
    mock_response = mocker.Mock()
    mock_response.status_code = 503
    mock_response.text = "Service Unavailable"
    mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "", 0)
    
    mocker.patch("requests.get", return_value=mock_response)
    
    # 503 응답 시 JSONDecodeError가 아닌 StockAutoException으로 예외가 던져져야 함
    with pytest.raises(StockAutoException) as excinfo:
        api.get_account_balance(exchange_rate=1400.0)
        
    assert excinfo.value.status_code == 502
