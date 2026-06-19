import pytest
from fastapi import FastAPI, APIRouter, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel
from app.core.response import SuccessResponseRoute, success_response

app = FastAPI()

# Apply the custom route class to a router
router = APIRouter(route_class=SuccessResponseRoute)

class Item(BaseModel):
    id: int
    name: str


class Token(BaseModel):
    access_token: str

@router.get("/dict")
def get_dict():
    return {"key": "value"}

@router.get("/string")
def get_string():
    return "just a string"

@router.get("/list")
def get_list():
    return [{"id": 1}, {"id": 2}]

@router.get("/pydantic")
def get_pydantic():
    return Item(id=1, name="test item")

@router.get("/already_wrapped")
def get_already_wrapped():
    # If a developer manually wraps it using success_response, it shouldn't be double wrapped
    return success_response(data={"manual": "wrap"})


@router.get("/message")
def get_message():
    return {"message": "custom done"}


@router.get("/message_with_data")
def get_message_with_data():
    return {"message": "custom done", "data": {"value": 1}}


@router.get("/response_model", response_model=Token)
def get_response_model(response: Response):
    response.set_cookie("refresh_token", "abc", path="/api/v1/auth")
    return {"access_token": "token-value"}

app.include_router(router)

client = TestClient(app)

def test_dict_response():
    response = client.get("/dict")
    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == {"key": "value"}

def test_string_response():
    response = client.get("/string")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == "just a string"

def test_list_response():
    response = client.get("/list")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == [{"id": 1}, {"id": 2}]

def test_pydantic_response():
    response = client.get("/pydantic")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == {"id": 1, "name": "test item"}

def test_already_wrapped_response():
    response = client.get("/already_wrapped")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == {"manual": "wrap"}
    # Verify it doesn't have nested data like data["data"]["data"]
    assert "code" not in data["data"]


def test_message_response_promotes_message():
    response = client.get("/message")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "custom done"
    assert data["data"] is None


def test_message_with_data_response_promotes_message_and_data():
    response = client.get("/message_with_data")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "custom done"
    assert data["data"] == {"value": 1}


def test_response_model_response_is_wrapped_and_preserves_cookie():
    response = client.get("/response_model")
    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
    assert response.cookies.get("refresh_token") == "abc"
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert data["message"] == "요청이 성공적으로 처리되었습니다."
    assert data["data"] == {"access_token": "token-value"}

if __name__ == "__main__":
    pytest.main(["-v", __file__])
