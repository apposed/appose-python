# Appose Python

***WARNING: Appose is currently in incubation.
Not all features described below are functional.
This document has some aspirational aspects!***

## What is Appose?

Appose is a library for interprocess cooperation with shared memory.
The guiding principles are *simplicity* and *efficiency*.

Appose was written to enable **easy execution of Python-based deep learning
from Java without copying tensors**, but its utility extends beyond that.
The steps for using Appose are:

* Build an Environment with the dependencies you need.
* Create a Service linked to a *worker*, which runs in its own process.
* Execute scripts on the worker by launching Tasks.
* Receive status updates from the task asynchronously via callbacks.

For more about Appose as a whole, see https://apposed.org.

## What is this project?

This is the **Python implementation of Appose**.

## How do I use it?

The name of the package is `appose`.

### Conda/Mamba

To use [the conda-forge package](https://anaconda.org/conda-forge/appose),
add `appose` to your `environment.yml`'s `dependencies` section:

```yaml
dependencies:
  - appose
```

### PyPI/Pip

To use [the PyPI package](https://pypi.org/project/appose),
add `appose` to your project dependencies.

Depending on how your project is set up, this might entail editing
`requirements.txt`, `setup.py`, `setup.cfg`, and/or `pyproject.toml`.

If you are just starting out, we recommend using `pyproject.toml` (see
[this guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/#creating-pyproject-toml)):

```toml
dependencies = [
  "appose"
]
```

## Examples

Here is a minimal example for calling into Java from Python:

```python
import appose
env = appose.java(vendor="zulu", version="17").build()
with env.groovy() as groovy:
    task = groovy.task("5 + 6")
    task.waitFor()
    result = task.outputs.get("result")
    assert 11 == result
```

*Note: The `Appose.java` builder is planned, but not yet implemented.*

Here is an example using a few more of Appose's features:

```python
import appose
from time import sleep

golden_ratio_in_groovy = """
// Approximate the golden ratio using the Fibonacci sequence.
previous = 0
current = 1
for (i=0; i<iterations; i++) {
    if (task.cancelRequested) {
        task.cancel()
        break
    }
    task.update(null, i, iterations)
    v = current
    current += previous
    previous = v
}
task.outputs["numer"] = current
task.outputs["denom"] = previous
"""

env = appose.java(vendor="zulu", version="17").build()
with env.groovy() as groovy:
    task = groovy.task(golden_ratio_in_groovy)

    def task_listener(event):
        match event.responseType:
            case ResponseType.UPDATE:
                print(f"Progress {task.current}/{task.maximum}")
            case ResponseType.COMPLETION:
                numer = task.outputs["numer"]
                denom = task.outputs["denom"]
                ratio = numer / denom
                print(f"Task complete. Result: {numer}/{denom} =~ {ratio}");
            case ResponseType.CANCELATION:
                print("Task canceled")
            case ResponseType.FAILURE:
                print(f"Task failed: {task.error}")

    task.listen(task_listener)

    task.start()
    sleep(1)
    if not task.status.is_finished():
        # Task is taking too long; request a cancelation.
        task.cancel()

    task.wait_for()
```

Of course, the above examples could have been done all in one language. But
hopefully they hint at the possibilities of easy cross-language integration.
