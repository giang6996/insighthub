import json
import pathlib
import unittest
from typing import Optional


ROOT = pathlib.Path(__file__).resolve().parents[3]


def deployment_is_safe(ingress: Optional[str] = None) -> bool:
    ingress = ingress or (ROOT / "deploy" / "web-ingress.yaml").read_text(encoding="utf-8")
    api = (ROOT / "deploy" / "api-deployment.yaml").read_text(encoding="utf-8")
    return (
        "name: web" in ingress
        and "name: api" not in ingress
        and "internet-facing" in ingress
        and "target-type: ip" in ingress
        and ":latest" not in api
    )


class Day3PolicyTests(unittest.TestCase):
    def test_policy_allows_valid(self):
        policy = json.loads(
            (ROOT / "infra/policies/aws-load-balancer-controller-v2.8.3.json").read_text()
        )
        actions = {action for statement in policy["Statement"] for action in statement["Action"]}
        self.assertTrue(deployment_is_safe())
        self.assertIn("elasticloadbalancing:CreateLoadBalancer", actions)
        self.assertNotIn("iam:PassRole", actions)

    def test_policy_denies_unsafe(self):
        unsafe_ingress = (ROOT / "deploy" / "web-ingress.yaml").read_text(encoding="utf-8").replace(
            "name: web", "name: api", 1
        )
        self.assertFalse(deployment_is_safe(unsafe_ingress))


if __name__ == "__main__":
    unittest.main()
