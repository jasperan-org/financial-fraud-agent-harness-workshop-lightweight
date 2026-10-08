"""Chat LLM setup: credentials from the environment and an OpenAI-compatible `chat()` helper."""
import getpass
import os
import sys
import time
from pathlib import Path

from openai import OpenAI, RateLimitError


def _import_key_rotation():
    root = next((p for p in [Path.cwd(), *Path.cwd().parents]
                 if (p / "oci_key_rotation.py").exists()), None)
    if root is None:
        raise RuntimeError("Run this notebook from the workshop repository")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import oci_key_rotation
    return oci_key_rotation


def configure_llm():
    """Read or prompt for credentials. Returns (provider, rotator, oci_endpoint, oci_compartment_id).

    `rotator` is the OCI key rotator, or None for the OpenAI provider.
    """
    kr = _import_key_rotation()
    provider = os.environ.setdefault("LLM_PROVIDER", "oci").lower()
    assert provider in ("openai", "oci"), "LLM_PROVIDER must be 'openai' or 'oci'"
    rotator = None
    if provider == "oci":
        if not kr.load_oci_keys():
            os.environ["OCI_GENAI_API_KEY"] = getpass.getpass("OCI GenAI API key: ")
        os.environ.setdefault(
            "OCI_GENAI_ENDPOINT",
            "https://inference.generativeai.us-phoenix-1.oci.oraclecloud.com/openai/v1",
        )
        os.environ.setdefault("LLM_MODEL", "xai.grok-4.3")
        rotator = kr.KeyRotator(kr.load_oci_keys())
        print(f"OCI key rotation enabled: {len(rotator)} key(s), starting at key #{rotator.current_index() + 1}")
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = getpass.getpass("OpenAI API key: ")
        os.environ.setdefault("LLM_MODEL", "gpt-5.5")
    endpoint = os.environ.get("OCI_GENAI_ENDPOINT", "").rstrip("/")
    if provider == "oci" and not endpoint.endswith("/openai/v1"):
        endpoint = f"{endpoint}/openai/v1"
        os.environ["OCI_GENAI_ENDPOINT"] = endpoint
    compartment = os.environ.get("OCI_COMPARTMENT_ID", "").strip()
    print(f"LLM: {provider}/{os.environ['LLM_MODEL']}")
    return provider, rotator, endpoint, compartment


RATE_LIMIT_BACKOFF = (15, 30, 60)   # seconds before retries 1-3; a Retry-After header wins


def _retry_rate_limit(call):
    """Run `call`, retrying a 429 up to three times with backoff and one short line per retry."""
    for delay in (*RATE_LIMIT_BACKOFF, None):
        try:
            return call()
        except RateLimitError as exc:
            if delay is None:
                raise
            try:
                delay = min(float(exc.response.headers["retry-after"]), 120.0)
            except (AttributeError, KeyError, TypeError, ValueError):
                pass
            print(f"  rate-limited, retrying in {delay:.0f} s")
            time.sleep(delay)


def make_chat(provider, model, rotator=None, endpoint="", compartment=""):
    """Build the OpenAI SDK client and a `chat(messages, tools=None)` function. Returns (llm, chat)."""
    from oci_key_rotation import call_with_failover

    def make_oci_client(key):
        options = {"base_url": endpoint, "api_key": key}
        if compartment:
            options["project"] = compartment
        return OpenAI(**options)

    llm = make_oci_client(rotator.current()) if provider == "oci" else OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def chat(messages, tools=None, model=model):
        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if provider == "oci":
            on_event = print if len(rotator) > 1 else None   # a one-key "switch" line is noise
            call = lambda: call_with_failover(make_oci_client, lambda client: client.chat.completions.create(**kwargs),
                                              rotator, base_delay=2.0, on_event=on_event)
        else:
            call = lambda: llm.chat.completions.create(**kwargs)
        return _retry_rate_limit(call)

    return llm, chat
