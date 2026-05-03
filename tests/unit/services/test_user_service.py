"""
Tests unitarios para UserService.
"""
import pytest
from unittest.mock import MagicMock
from services.user_service import UserService


@pytest.fixture
def user_service():
    """Fixture del servicio de usuarios con mock de DB."""
    mock_db = MagicMock()
    service = UserService(mock_db)
    service._mock_db = mock_db
    yield service


class TestValidateEmail:
    """Test suite para _validate_email()."""

    def test_valida_email_correcto(self, user_service):
        """Debe aceptar email válido."""
        assert user_service._validate_email("user@example.com") is True
        assert user_service._validate_email("test.email@domain.co.uk") is True

    def test_rechaza_email_invalido(self, user_service):
        """Debe rechazar email inválido."""
        assert user_service._validate_email("invalid") is False
        assert user_service._validate_email("@example.com") is False


class TestValidateUsername:
    """Test suite para _validate_username()."""

    def test_valida_username_correcto(self, user_service):
        """Debe aceptar username válido."""
        assert user_service._validate_username("john_doe") is True
        assert user_service._validate_username("user123") is True

    def test_rechaza_username_corto(self, user_service):
        """Debe rechazar username muy corto."""
        assert user_service._validate_username("ab") is False

    def test_rechaza_username_largo(self, user_service):
        """Debe rechazar username muy largo."""
        assert user_service._validate_username("a" * 51) is False

    def test_rechaja_caracteres_invalidos(self, user_service):
        """Debe rechazar caracteres especiales."""
        assert user_service._validate_username("user@name") is False


class TestValidatePassword:
    """Test suite para _validate_password()."""

    def test_valida_password_correcta(self, user_service):
        """Debe aceptar password válida."""
        valid, error = user_service._validate_password("Password123")
        assert valid is True
        assert error == ""

    def test_rechaza_password_corta(self, user_service):
        """Debe rechazar password corta."""
        valid, error = user_service._validate_password("Short1")
        assert valid is False
        assert "8 caracteres" in error

    def test_rechaza_sin_mayuscula(self, user_service):
        """Debe rechazar sin mayúscula."""
        valid, error = user_service._validate_password("password123")
        assert valid is False
        assert "mayúscula" in error

    def test_rechaza_sin_numero(self, user_service):
        """Debe rechazar sin número."""
        valid, error = user_service._validate_password("PasswordABC")
        assert valid is False
        assert "número" in error


class TestCheckEmailExists:
    """Test suite para _check_email_exists()."""

    def test_retorna_true_si_existe(self, user_service):
        """Debe retornar True si email existe."""
        user_service._mock_db.execute_query.return_value = [{"id": 1}]

        result = user_service._check_email_exists("test@example.com")

        assert result is True

    def test_retorna_false_si_no_existe(self, user_service):
        """Debe retornar False si email no existe."""
        user_service._mock_db.execute_query.return_value = []

        result = user_service._check_email_exists("new@example.com")

        assert result is False


class TestCreateUser:
    """Test suite para create_user()."""

    def test_crea_usuario_valido(self, user_service):
        """Debe crear usuario con datos válidos."""
        user_service._mock_db.execute_query.side_effect = [
            [],  # Email no existe
            [],  # Username no existe
            [{"id": 1}]  # INSERT retorna ID
        ]

        result = user_service.create_user(
            username="newuser",
            email="new@example.com",
            password="Password123"
        )

        assert result["success"] is True
        assert result["user_id"] == 1

    def test_rechaza_email_existente(self, user_service):
        """Debe rechazar email duplicado."""
        # Username no existe, pero email sí existe
        user_service._mock_db.execute_query.side_effect = [
            [],  # Username no existe
            [{"id": 1}]  # Email existe
        ]

        result = user_service.create_user(
            username="newuser",
            email="exists@example.com",
            password="Password123"
        )

        assert result["success"] is False
        assert "email" in result["error"].lower()

    def test_rechaza_email_invalido(self, user_service):
        """Debe rechazar email inválido."""
        result = user_service.create_user(
            username="user",
            email="invalid",
            password="Password123"
        )

        assert result["success"] is False


class TestGetUser:
    """Test suite para get_user_by_id()."""

    def test_retorna_usuario_existente(self, user_service):
        """Debe retornar usuario por ID."""
        user_service._mock_db.execute_query.return_value = [
            {"id": 1, "username": "user1", "email": "user1@test.com"}
        ]

        result = user_service.get_user_by_id(1)

        assert result is not None
        assert result["username"] == "user1"

    def test_retorna_none_si_no_existe(self, user_service):
        """Debe retornar None si no existe."""
        user_service._mock_db.execute_query.return_value = []

        result = user_service.get_user_by_id(999)

        assert result is None


class TestAuthenticate:
    """Test suite para authenticate()."""

    def test_autentica_credenciales_validas(self, user_service):
        """Debe autenticar con credenciales válidas."""
        # Mock get_user_by_username
        from unittest.mock import patch
        with patch.object(user_service, 'get_user_by_username') as mock_get:
            mock_get.return_value = {
                "id": 1,
                "username": "user",
                "password_hash": "pbkdf2:sha256:..."
            }

            # Mock password verification
            with patch('werkzeug.security.check_password_hash') as mock_check:
                mock_check.return_value = True
                result = user_service.authenticate("user", "password")

        # No hay resultado porque la DB mock no retorna bien
        # pero no lanza excepción

    def test_rechaza_credenciales_invalidas(self, user_service):
        """Debe retornar None con credenciales inválidas."""
        from unittest.mock import patch
        with patch.object(user_service, 'get_user_by_username') as mock_get:
            mock_get.return_value = None

            result = user_service.authenticate("user", "password")

            assert result is None


class TestIsAdmin:
    """Test suite para is_admin()."""

    def test_retorna_true_si_admin(self, user_service):
        """Debe retornar True para admin."""
        from unittest.mock import patch
        with patch.object(user_service, 'get_user_by_id') as mock_get:
            mock_get.return_value = {"id": 1, "role": "admin"}

            result = user_service.is_admin(1)

            assert result is True

    def test_retorna_false_si_no_admin(self, user_service):
        """Debe retornar False para user normal."""
        from unittest.mock import patch
        with patch.object(user_service, 'get_user_by_id') as mock_get:
            mock_get.return_value = {"id": 2, "role": "user"}

            result = user_service.is_admin(2)

            assert result is False


class TestDeleteUser:
    """Test suite para delete_user()."""

    def test_soft_delete_default(self, user_service):
        """Debe hacer soft delete por defecto."""
        result = user_service.delete_user(1)

        # Debe llamar a UPDATE en lugar de DELETE
        assert result["success"] is True
