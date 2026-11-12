"""Тесты входа на портал."""

import pytest
from django.urls import reverse

from accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    """Активный пользователь портала с обычным паролем."""
    return User.objects.create_user(
        username='ivanov',
        password='secret-pass-123',
    )


def test_login_page_shows_mode_switch(client):
    """На странице входа есть переключатель режимов."""
    response = client.get(reverse('accounts:login'))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'Учётная запись портала' in content
    assert 'Active Directory' in content


def test_local_login_success(client, user):
    """Вход по учётной записи портала ведёт к списку документов."""
    response = client.post(
        reverse('accounts:login'),
        {
            'username': 'ivanov',
            'password': 'secret-pass-123',
            'auth_source': 'local',
        },
    )
    assert response.status_code == 302
    assert response.url == reverse('documents:list')
    assert client.session['_auth_user_id'] == str(user.pk)


def test_wrong_password_not_logged_in(client, user):
    """Неверный пароль не пускает на портал."""
    response = client.post(
        reverse('accounts:login'),
        {
            'username': 'ivanov',
            'password': 'wrong-pass',
            'auth_source': 'local',
        },
    )
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session


def test_ad_login_rejected(client, user):
    """Режим Active Directory пока не поддерживается."""
    response = client.post(
        reverse('accounts:login'),
        {
            'username': 'ivanov',
            'password': 'secret-pass-123',
            'auth_source': 'ad',
        },
    )
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session
    assert 'Active Directory' in response.content.decode()


def test_inactive_user_cannot_login(client):
    """Заблокированный пользователь не может войти."""
    User.objects.create_user(
        username='petrov',
        password='secret-pass-123',
        is_active=False,
    )
    response = client.post(
        reverse('accounts:login'),
        {
            'username': 'petrov',
            'password': 'secret-pass-123',
            'auth_source': 'local',
        },
    )
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session
