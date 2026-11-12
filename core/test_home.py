"""Тесты главной страницы портала."""

import pytest
from django.urls import reverse

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_home_requires_login(client):
    """Гость с главной страницы уходит на форму входа."""
    response = client.get(reverse('core:home'))
    assert response.status_code == 302
    assert reverse('accounts:login') in response.url


def test_home_renders_for_authenticated_user(client):
    """Вошедший сотрудник видит главную страницу портала."""
    user = User.objects.create_user(
        username='sidorov',
        password='secret-pass-123',
    )
    client.force_login(user)

    response = client.get(reverse('core:home'))

    assert response.status_code == 200
    assert 'Разделы портала' in response.content.decode()
