from django.contrib.auth import get_user_model
from django.test import Client

import pytest


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
    )


@pytest.fixture
def admin_client(client, superuser):
    client.force_login(superuser)
    return client
