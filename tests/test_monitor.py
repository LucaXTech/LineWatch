import unittest
from unittest.mock import patch

import monitor


class MonitorTests(unittest.TestCase):
    def sample(self, **overrides):
        values = dict(
            ts="2026-09-05T12:00:00+00:00",
            carrier=1,
            gateway="192.168.1.1",
            gateway_ok=1,
            gateway_ms=1.2,
            internet_ok=1,
            internet_ms=10.0,
            dns_ok=1,
            dns_ms=8.0,
            http_ok=1,
            http_ms=30.0,
            public_ip="203.0.113.10",
            router_uptime_s=None,
            router_model=None,
            fritzos=None,
            wan_status=None,
            wan_uptime_s=None,
            wan_ip=None,
            wan_last_error=None,
            wan_transport=None,
            pppoe_ac_name=None,
            fritz_error=None,
        )
        values.update(overrides)
        return monitor.Sample(**values)

    def test_auto_router_mode_defaults_to_generic_without_credentials(self):
        self.assertEqual(
            monitor.resolve_router_mode("auto", user="", password=""), "generic"
        )

    def test_auto_router_mode_enables_fritz_when_credentials_exist(self):
        self.assertEqual(
            monitor.resolve_router_mode("auto", user="user", password="secret"),
            "fritz",
        )

    def test_explicit_fritz_mode_requires_credentials(self):
        with self.assertRaises(ValueError):
            monitor.resolve_router_mode("fritz", user="", password="")

    def test_gateway_probe_modes(self):
        self.assertIsNone(monitor.resolve_gateway_probe("auto"))
        self.assertTrue(monitor.resolve_gateway_probe("on"))
        self.assertFalse(monitor.resolve_gateway_probe("off"))
        with self.assertRaises(ValueError):
            monitor.resolve_gateway_probe("invalid")

    def test_failed_gateway_ping_is_not_an_outage_when_internet_is_healthy(self):
        sample = self.sample(gateway_ok=0, gateway_ms=None, internet_ok=0, internet_ms=None)
        self.assertEqual(monitor.classify(sample, gateway_probe_active=True), "OK")

    def test_gateway_unreachable_when_probe_is_supported_and_all_paths_fail(self):
        sample = self.sample(
            gateway_ok=0,
            gateway_ms=None,
            internet_ok=0,
            internet_ms=None,
            dns_ok=0,
            dns_ms=None,
            http_ok=0,
            http_ms=None,
        )
        self.assertEqual(
            monitor.classify(sample, gateway_probe_active=True),
            "GATEWAY_UNREACHABLE",
        )

    def test_generic_outage_when_gateway_probe_is_disabled(self):
        sample = self.sample(
            gateway_ok=0,
            gateway_ms=None,
            internet_ok=0,
            internet_ms=None,
            dns_ok=0,
            dns_ms=None,
            http_ok=0,
            http_ms=None,
        )
        self.assertEqual(
            monitor.classify(sample, gateway_probe_active=False),
            "INTERNET_UNREACHABLE",
        )

    def test_link_down_has_highest_priority(self):
        sample = self.sample(carrier=0)
        self.assertEqual(monitor.classify(sample), "NETWORK_LINK_DOWN")

    def test_wan_session_down_is_detected_with_router_telemetry(self):
        sample = self.sample(wan_status="Disconnected")
        self.assertEqual(monitor.classify(sample), "WAN_SESSION_DOWN")

    def test_dns_failure_is_separate_from_internet_outage(self):
        sample = self.sample(dns_ok=0, dns_ms=None)
        self.assertEqual(monitor.classify(sample), "DNS_FAILURE")

    def test_http_failure_is_separate_from_internet_outage(self):
        sample = self.sample(http_ok=0, http_ms=None)
        self.assertEqual(monitor.classify(sample), "HTTP_CONNECTIVITY_FAILURE")

    @patch.object(
        monitor.subprocess,
        "check_output",
        return_value="default via 192.168.178.1 dev enp3s0 proto dhcp src 192.168.178.20\n",
    )
    def test_default_route_detects_gateway_and_interface(self, _):
        self.assertEqual(monitor.default_route(), ("192.168.178.1", "enp3s0"))


if __name__ == "__main__":
    unittest.main()
