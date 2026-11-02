"""The SMS line: a basic phone asks « is it checked? » and receives the signed verdict."""

from fastapi import APIRouter

router = APIRouter(tags=["sms"])
