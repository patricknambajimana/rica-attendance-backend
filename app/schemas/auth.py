from pydantic import AliasChoices, BaseModel, Field, field_validator

from ..utils.validators import validate_password


class LoginIn(BaseModel):
    # The client may send the value as "identifier", "username" or "email".
    identifier: str = Field(min_length=1, validation_alias=AliasChoices("identifier", "username", "email"))
    password: str = Field(min_length=1)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password(v)


class ForgotPasswordIn(BaseModel):
    identifier: str = Field(min_length=1, validation_alias=AliasChoices("identifier", "username", "email"))


class ResetPasswordWithTokenIn(BaseModel):
    token: str = Field(min_length=1)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password(v)