"""Adversarial tests for the untrusted-input boundary.

Users load `.archimate` files they did not author, so the model-loading path is
the one place where hostile input reaches this server directly. These tests
attack it rather than asserting that the guards exist.

The canary pattern matters here: asserting only that an exception is raised
would still pass if the guard were replaced by something that read the file and
*then* failed. Every payload below points at a real file with known contents,
and the tests assert those contents never surface.
"""

import asyncio

import pytest
from lxml import etree

from pyarchimate_mcp_server.exceptions import ModelOperationError
from pyarchimate_mcp_server.model_manager import (
    MAX_MODEL_CONTENT_BYTES,
    ArchimateModelManager,
)
from pyarchimate_mcp_server.tools import workflow_tools

CANARY = "CANARY_SECRET_9f3a2b"

# Payloads below use a real ArchiMate root on purpose. With a junk root element
# the root-tag allow-list in `_validate_xml_content` rejects them first, and the
# tests would pass while proving nothing about entity handling. A genuine
# attacker would use a well-formed root, so the tests do too — that leaves the
# DTD/entity rejection as the only thing standing between the payload and
# pyArchimate's reader.
ARCHIMATE_ROOT_OPEN = '<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/">'
ARCHIMATE_ROOT_CLOSE = "</model>"


@pytest.fixture
def canary_file(tmp_path):
    """A file whose contents must never appear in a loaded model."""
    path = tmp_path / "canary.txt"
    path.write_text(CANARY, encoding="utf-8")
    return path


def test_xxe_payload_is_genuinely_dangerous(canary_file):
    """Guard the guards: prove the payload used below is a working attack.

    If lxml ever stops leaking here, these tests would keep passing while
    testing nothing, so this asserts the exploit works against a deliberately
    permissive parser. It is the control case for every test that follows.
    """
    payload = (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE model [<!ENTITY xxe SYSTEM "file://{canary_file}">]>\n'
        "<model>&xxe;</model>\n"
    )
    permissive = etree.XMLParser(load_dtd=True, resolve_entities=True, no_network=False)

    root = etree.fromstring(payload.encode("utf-8"), parser=permissive)

    assert CANARY in (root.text or ""), (
        "the XXE payload no longer leaks even under a permissive parser, so the "
        "tests below no longer prove anything — replace the payload"
    )


INLINE_SYSTEM_ENTITY = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE model [<!ENTITY xxe SYSTEM "file://{path}">]>\n'
    f"{ARCHIMATE_ROOT_OPEN}<documentation>&xxe;</documentation>"
    f"{ARCHIMATE_ROOT_CLOSE}\n"
)

EXTERNAL_DTD = (
    '<?xml version="1.0"?>\n'
    '<!DOCTYPE model SYSTEM "file://{path}">\n'
    f"{ARCHIMATE_ROOT_OPEN}{ARCHIMATE_ROOT_CLOSE}\n"
)

PARAMETER_ENTITY = (
    '<?xml version="1.0"?>\n'
    "<!DOCTYPE model [\n"
    '  <!ENTITY % ext SYSTEM "file://{path}">\n'
    "  %ext;\n"
    "]>\n"
    f"{ARCHIMATE_ROOT_OPEN}{ARCHIMATE_ROOT_CLOSE}\n"
)

LOWERCASE_DOCTYPE = (
    '<?xml version="1.0"?>\n'
    '<!doctype model [<!entity xxe SYSTEM "file://{path}">]>\n'
    f"{ARCHIMATE_ROOT_OPEN}<documentation>&xxe;</documentation>"
    f"{ARCHIMATE_ROOT_CLOSE}\n"
)


@pytest.mark.parametrize(
    ("label", "template"),
    [
        ("inline system entity", INLINE_SYSTEM_ENTITY),
        ("external dtd on the doctype itself", EXTERNAL_DTD),
        ("parameter entity", PARAMETER_ENTITY),
        ("lowercase doctype", LOWERCASE_DOCTYPE),
    ],
)
def test_load_from_string_rejects_entity_payloads(canary_file, label, template):
    manager = ArchimateModelManager()
    payload = template.format(path=canary_file)

    with pytest.raises(ModelOperationError) as excinfo:
        manager.load_model_from_string(payload)

    assert CANARY not in str(excinfo.value), f"{label}: canary leaked into the error"
    assert manager.get_active_model() is None, (
        f"{label}: a model was left active after a rejected load"
    )


def test_load_from_string_rejects_billion_laughs():
    """Entity-expansion denial of service, using only internal entities."""
    entities = "".join(
        f'<!ENTITY lol{i} "{f"&lol{i - 1};" * 10}">' for i in range(1, 8)
    )
    bomb = (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE lolz [<!ENTITY lol "lol">{entities}]>'
        "<lolz>&lol7;</lolz>"
    )
    manager = ArchimateModelManager()

    with pytest.raises(ModelOperationError):
        manager.load_model_from_string(bomb)


def test_load_from_string_rejects_oversized_content():
    manager = ArchimateModelManager()
    oversized = "<model>" + ("x" * (MAX_MODEL_CONTENT_BYTES + 1)) + "</model>"

    with pytest.raises(ModelOperationError, match="maximum supported size"):
        manager.load_model_from_string(oversized)


def test_load_model_from_file_rejects_xxe_end_to_end(
    tmp_path,
    canary_file,
    monkeypatch,
):
    """The file path must be no weaker than the string path.

    `load_model_from_file` reads the file itself before delegating, so this
    would catch a future refactor that handed the path straight to pyArchimate
    and skipped validation.
    """
    hostile = tmp_path / "hostile.archimate"
    hostile.write_text(
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE model [<!ENTITY xxe SYSTEM "file://{canary_file}">]>\n'
        f"{ARCHIMATE_ROOT_OPEN}<documentation>&xxe;</documentation>"
        f"{ARCHIMATE_ROOT_CLOSE}\n",
        encoding="utf-8",
    )
    manager = ArchimateModelManager()
    monkeypatch.setattr(workflow_tools, "_model_manager", lambda: manager)

    response = asyncio.run(workflow_tools.load_model_from_file(str(hostile)))

    assert response["status"] == "error"
    assert CANARY not in str(response), "canary leaked through the file-loading tool"
    assert manager.get_active_model() is None


def test_benign_doctype_free_model_still_loads():
    """The DTD rejection must not be so broad that real models stop loading."""
    source = ArchimateModelManager()
    source.create_new_model("Security Baseline")
    source.add_archimate_element("Customer", "BusinessActor")
    content = source.get_model_content_as_string("archi")

    loaded = ArchimateModelManager()
    loaded.load_model_from_string(content, "archi")

    assert loaded.get_active_model().name == "Security Baseline"
