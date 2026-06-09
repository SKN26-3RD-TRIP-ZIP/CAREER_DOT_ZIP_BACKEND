from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.services.ai_chain_persona_prompts import (
    get_persona_options,
    normalize_persona_type,
)


class InterviewPersonaAPITest(APITestCase):
    def test_get_persona_options_returns_three_official_personas(self):
        personas = get_persona_options()

        self.assertEqual(len(personas), 3)
        self.assertEqual(
            [persona["persona_type"] for persona in personas],
            ["friendly", "practical", "verify"],
        )

    def test_persona_aliases_are_normalized_to_official_types(self):
        self.assertEqual(normalize_persona_type("coach"), "friendly")
        self.assertEqual(normalize_persona_type("strict"), "verify")
        self.assertEqual(normalize_persona_type("unknown"), "practical")

    def test_persona_list_api_returns_three_personas(self):
        url = reverse("interview-persona-list")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(
            [persona["persona_type"] for persona in response.data["results"]],
            ["friendly", "practical", "verify"],
        )
        self.assertIn("label", response.data["results"][0])
        self.assertIn("description", response.data["results"][0])
        self.assertIn("usage_guide", response.data["results"][0])
