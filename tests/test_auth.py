import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from jose import jwt

from app.config import settings
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import LoginInput, RegisterInput, TokenOutput, UserInfo
from app.middleware.auth import verify_token, get_current_user


class TestAuthService:
    @patch("app.modules.auth.service.pwd_context")
    def test_password_hashing(self, mock_pwd):
        mock_pwd.hash.return_value = "$2b$12$hashed_value"
        mock_pwd.verify.return_value = True
        password = "test123456"
        hashed = auth_service._hash_password(password)
        assert hashed == "$2b$12$hashed_value"
        assert auth_service._verify_password(password, hashed)

    @patch("app.modules.auth.service.pwd_context")
    def test_password_verification_fails(self, mock_pwd):
        mock_pwd.hash.return_value = "$2b$12$hashed_value"
        mock_pwd.verify.return_value = False
        hashed = auth_service._hash_password("correct_password")
        assert not auth_service._verify_password("wrong_password", hashed)

    def test_create_access_token(self):
        token = auth_service._create_access_token(user_id=1, role="user")
        assert isinstance(token, str)
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        assert payload["user_id"] == 1
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        token = auth_service._create_refresh_token(user_id=1)
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        assert payload["type"] == "refresh"

    def test_access_token_has_role(self):
        token = auth_service._create_access_token(user_id=1, role="admin")
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        assert payload["role"] == "admin"

    def test_access_token_expiry(self):
        token = auth_service._create_access_token(user_id=1, role="user")
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        exp = datetime.fromtimestamp(payload["exp"])
        diff = exp - datetime.now()
        assert timedelta(minutes=25) < diff < timedelta(minutes=35)

    def test_refresh_token_expiry(self):
        token = auth_service._create_refresh_token(user_id=1)
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        exp = datetime.fromtimestamp(payload["exp"])
        diff = exp - datetime.now()
        assert timedelta(days=6) < diff < timedelta(days=8)

    def test_token_user_id_type(self):
        token = auth_service._create_access_token(user_id=999, role="user")
        payload = jwt.decode(token, settings.jwt_secret_key,
                             algorithms=[settings.jwt_algorithm])
        assert isinstance(payload["user_id"], int)


class TestVerifyToken:
    def test_valid_token(self):
        token = jwt.encode(
            {"user_id": 1, "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        mock_credentials = MagicMock()
        mock_credentials.credentials = token
        payload = verify_token(mock_credentials)
        assert payload["user_id"] == 1

    def test_expired_token(self):
        token = jwt.encode(
            {"user_id": 1, "exp": datetime.utcnow() - timedelta(hours=1)},
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        mock_credentials = MagicMock()
        mock_credentials.credentials = token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_token(mock_credentials)
        assert exc.value.status_code == 401

    def test_invalid_signature(self):
        token = jwt.encode(
            {"user_id": 1},
            "wrong_secret", algorithm="HS256",
        )
        mock_credentials = MagicMock()
        mock_credentials.credentials = token
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            verify_token(mock_credentials)

    def test_malformed_token(self):
        mock_credentials = MagicMock()
        mock_credentials.credentials = "not.a.token"
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            verify_token(mock_credentials)


class TestLogin:
    def test_login_user_not_found(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        from app.common.exceptions import BusinessException
        with pytest.raises(BusinessException) as exc:
            auth_service.login(mock_db, "unknown", "password")
        assert exc.value.error_code == 40101

    @patch("app.modules.auth.service._verify_password")
    def test_login_wrong_password(self, mock_verify, mock_db):
        mock_verify.return_value = False
        from tests.conftest import MockUser
        mock_db.query.return_value.filter.return_value.first.return_value = \
            MockUser(password_hash="$2b$12$fakehash")
        from app.common.exceptions import BusinessException
        with pytest.raises(BusinessException) as exc:
            auth_service.login(mock_db, "testuser", "wrongpassword")
        assert exc.value.error_code == 40102

    @patch("app.modules.auth.service._verify_password")
    def test_login_disabled_user(self, mock_verify, mock_db):
        mock_verify.return_value = True
        from tests.conftest import MockUser
        mock_user = MockUser(password_hash="$2b$12$fakehash", status="disabled")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        from app.common.exceptions import BusinessException
        with pytest.raises(BusinessException) as exc:
            auth_service.login(mock_db, "testuser", "pass")
        assert exc.value.status_code == 403

    @patch("app.modules.auth.service._verify_password")
    @patch("app.modules.auth.service._create_access_token")
    @patch("app.modules.auth.service._create_refresh_token")
    def test_login_success_returns_tokens(self, mock_refresh, mock_access, mock_verify, mock_db):
        mock_verify.return_value = True
        mock_access.return_value = "access_token_value"
        mock_refresh.return_value = "refresh_token_value"
        from tests.conftest import MockUser
        mock_user = MockUser(password_hash="$2b$12$fakehash")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        result = auth_service.login(mock_db, "testuser", "pass")
        assert result["access_token"] == "access_token_value"
        assert result["refresh_token"] == "refresh_token_value"
        assert "user" in result


class TestRegister:
    def test_register_duplicate_username(self, mock_db):
        from tests.conftest import MockUser
        mock_db.query.return_value.filter.return_value.first.return_value = MockUser()
        from app.common.exceptions import BusinessException
        with pytest.raises(BusinessException) as exc:
            auth_service.register(mock_db, RegisterInput(
                username="existing", email="new@test.com", password="123456", role="user",
            ))
        assert exc.value.error_code == 40901

    @patch("app.modules.auth.service._hash_password")
    def test_register_success(self, mock_hash, mock_db):
        mock_hash.return_value = "$2b$12$hashed_value"
        mock_db.query.return_value.filter.return_value.first.side_effect = [None, None]

        def _refresh(user):
            user.id = 1

        mock_db.refresh.side_effect = _refresh
        result = auth_service.register(mock_db, RegisterInput(
            username="newuser", email="new@test.com", password="123456", role="user",
        ))
        assert result.username == "newuser"
        assert result.role == "user"
        assert result.id == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestLoginInputValidation:
    def test_valid_credentials(self):
        form = LoginInput(username="admin", password="123456")
        assert form.username == "admin"
        assert form.password == "123456"

    def test_username_as_email(self):
        form = LoginInput(username="user@test.com", password="pass")
        assert form.username == "user@test.com"


class TestRegisterInputValidation:
    def test_valid_user_registration(self):
        form = RegisterInput(
            username="newuser", email="new@test.com",
            password="123456", role="user",
        )
        assert form.username == "newuser"
        assert form.role == "user"

    def test_admin_registration(self):
        form = RegisterInput(
            username="newadmin", email="admin@test.com",
            password="123456", role="admin",
        )
        assert form.role == "admin"
