"""MS #101531：任务 key 不得污染进程全局，澄清请求不得复用残留 key，401 返回可读文案。

运行：python3 -m unittest tests.test_task_key_scope
"""
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# config 在导入时会联网取时间，测试里直接让它失败回落到系统时间
with mock.patch("requests.get", side_effect=Exception), mock.patch("requests.head", side_effect=Exception):
    import config

from fastapi.testclient import TestClient
import openai
import httpx
from api import app as app_module
from agents.clarifier import ClarifierAgent

DEPLOY_KEY = "deploy-key"
DEPLOY_URL = "https://deploy.example/v1"


class TaskKeyScopeTest(unittest.TestCase):
    def setUp(self):
        self._saved = (config.API_KEY, config.API_BASE_URL, getattr(config, "ENV_API_KEY", ""))
        config.API_KEY, config.API_BASE_URL = DEPLOY_KEY, DEPLOY_URL

    def tearDown(self):
        config.API_KEY, config.API_BASE_URL, config.ENV_API_KEY = self._saved

    def _apply_in_task_thread(self, key, url):
        seen = {}

        def task():
            app_module._apply_task_runtime_config({"api_key": key, "base_url": url})
            seen["key"], seen["url"] = config.get_api_key(), config.get_base_url()

        t = threading.Thread(target=task)
        t.start()
        t.join()
        return seen

    def test_task_key_stays_in_task_thread(self):
        seen = self._apply_in_task_thread("llmk_task", "https://engine.example/api/llm-proxy/t/1")
        # 任务内拿到自己的 key
        self.assertEqual(seen["key"], "llmk_task")
        self.assertEqual(seen["url"], "https://engine.example/api/llm-proxy/t/1")
        # 任务结束后，进程全局与后续请求都不受影响
        self.assertEqual(config.API_KEY, DEPLOY_KEY)
        self.assertEqual(config.get_api_key(), DEPLOY_KEY)
        self.assertEqual(config.get_base_url(), DEPLOY_URL)
        agent = ClarifierAgent()
        self.assertEqual((agent.api_key, agent.base_url), (DEPLOY_KEY, DEPLOY_URL))

    def test_clarifier_prefers_request_key(self):
        agent = ClarifierAgent("req-key", "https://req.example")
        self.assertEqual((agent.api_key, agent.base_url), ("req-key", "https://req.example/v1"))

    def test_settings_cannot_override_env_key(self):
        config.ENV_API_KEY = DEPLOY_KEY
        with mock.patch("config.save_settings"):
            r = TestClient(app_module.app).post(
                "/api/settings", json={"api_key": "llmk_task", "base_url": "https://engine.example"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(config.API_KEY, DEPLOY_KEY)
        self.assertEqual(config.API_BASE_URL, DEPLOY_URL)

    def test_clarify_401_is_user_readable(self):
        err = openai.AuthenticationError(
            "Error code: 401 - {'error': 'invalid or expired key'}",
            response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
            body={"error": "invalid or expired key"},
        )
        with mock.patch.object(ClarifierAgent, "_call", side_effect=err):
            r = TestClient(app_module.app).post("/api/clarify", json={"question": "q"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], app_module._AUTH_EXPIRED_MSG)
        self.assertNotIn("invalid or expired key", r.text)


if __name__ == "__main__":
    unittest.main()
