"""
Smoke test of released Appose: run from outside the source tree, with appose
installed from PyPI, and appose-java's release in target/dependency.
"""

import sys

import appose

print(f"appose-python {appose.__version__}")


def worker_info(service):
    # NB: Releases predating the HELLO handshake lack worker_info().
    return service.worker_info() if hasattr(service, "worker_info") else "(unknown)"


# A Python worker, in an environment built as a user would.
env = appose.uv().include("cowsay").base("target/smoke-env").log_debug().build()
with env.python() as python:
    task = python.task("import cowsay\ncowsay.get_output_string('cow', 'moo')")
    output = task.wait_for().result()
    print(output)
    assert "moo" in output
    print(f"Python worker: {worker_info(python)}")

# A Groovy worker, from the appose-java release.
class_path = [sys.argv[1] + "/*"]
with appose.system().groovy(class_path=class_path) as groovy:
    assert groovy.task("6 * 7").wait_for().result() == 42
    print(f"Groovy worker: {worker_info(groovy)}")

print("Smoke test passed.")
