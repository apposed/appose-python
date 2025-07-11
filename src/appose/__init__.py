###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2025 Appose developers.
# %%
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# #L%
###

'''
Appose is a library for interprocess cooperation with shared memory.
The guiding principles are *simplicity* and *efficiency*.

Appose was written to enable **easy execution of Python-based deep learning
from Java without copying tensors**, but its utility extends beyond that.
The steps for using Appose are:

* Build an *environment* with the dependencies you need.
* Create a *service* linked to a *worker*, which runs in its own process.
* Execute scripts on the worker by launching *tasks*.
* Receive status updates from the task asynchronously via callbacks.

## Examples

Here is a very simple example written in Python:

    import appose
    env = appose.java(vendor="zulu", version="17").build()
    groovy = env.groovy()
    Task task = groovy.task("""
        5 + 6
    """)
    task.wait_for()
    result = task.outputs.get("result")
    assert 11 == result

And here is an example using a few more of Appose's features:

    import appose
    from time import sleep

    env = appose.java(vendor="zulu", version="17").build()
    groovy = env.groovy()
    task = groovy.task("""
        // Approximate the golden ratio using the Fibonacci sequence.
        previous = 0
        current = 1
        for (i = 0; i < iterations; i++) {
            if (task.cancelRequested) {
                task.cancel()
                break
            }
            task.status(null, i, iterations)
            v = current
            current += previous
            previous = v
        }
        task.outputs["numer"] = current
        task.outputs["denom"] = previous
    """)

    def task_listener(event):
        match event.responseType:
            case UPDATE:
                print(f"Progress {event.current}/{event.maximum}")
            case COMPLETION:
                numer = task.outputs["numer"]
                denom = task.outputs["denom"]
                ratio = numer / denom
                print(f"Task complete. Result: {numer}/{denom} =~ {ratio}");
            case CANCELATION:
                print("Task canceled")
            case FAILURE:
                print(f"Task failed: {task.error}")

    task.listen(task_listener)

    task.start()
    sleep(1)
    if not task.status.isFinished():
        # Task is taking too long; request a cancelation.
        task.cancel()

    task.wait_for()

Of course, the above examples could have been done all in Python. But
hopefully they hint at the possibilities of easy cross-language integration.

## Workers

A *worker* is a separate process created by Appose to do asynchronous
computation on behalf of the calling process. The calling process interacts
with a worker via its associated *service*.

Appose comes with built-in support for two worker implementations:
`python_worker` to run Python scripts, and `GroovyWorker` to run Groovy
scripts. These workers can be created easily by invoking the environment
object's `python()` and `groovy()` methods respectively.

But Appose is compatible with any program that abides by the
*Appose worker process contract*:

1. The worker must accept requests in Appose's request format on its
   standard input (stdin) stream.
2. The worker must issue responses in Appose's response format on its
   standard output (stdout) stream.

### Requests to worker from service

A *request* is a single line of JSON sent to the worker process via
its standard input stream. It has a `task` key taking the form of a
UUID, and a `requestType` key with one of the following values:

#### EXECUTE

Asynchronously execute a script within the worker process. E.g.:

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "requestType" : "EXECUTE",
       "script" : "task.outputs[\"result\"] = computeResult(gamma)\n",
       "inputs" : {"gamma": 2.2}
    }

#### CANCEL

Cancel a running script. E.g.:

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "requestType" : "CANCEL"
    }

### Responses from worker to service

A *response* is a single line of JSON with a `task` key taking the form
of a UUID, and a `responseType` key with one of the following values:

#### LAUNCH

A LAUNCH response is issued to confirm the success of an EXECUTE
request.

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "responseType" : "LAUNCH"
    }

#### UPDATE

An UPDATE response is issued to convey that a task has somehow made
progress. The UPDATE response typically comes bundled with a
`message` string indicating what has changed, `current` and/or
`maximum` progress indicators conveying the step the task has
reached, or both.

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "responseType" : "UPDATE",
       "message" : "Processing step 0 of 91",
       "current" : 0,
       "maximum" : 91
    }

#### COMPLETION

A COMPLETION response is issued to convey that a task has successfully
completed execution, as well as report the values of any task outputs.

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "responseType" : "COMPLETION",
       "outputs" : {"result" : 91}
    }

#### CANCELATION

A CANCELATION response is issued to confirm the success of a CANCEL
request.

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "responseType" : "CANCELATION"
    }

#### FAILURE

A FAILURE response is issued to convey that a task did not completely
and successfully execute, such as an exception being raised.

    {
       "task" : "87427f91-d193-4b25-8d35-e1292a34b5c4",
       "responseType" : "FAILURE",
       "error", "Invalid gamma value"
    }
'''

from pathlib import Path

from .environment import Builder, Environment
from .types import NDArray, SharedMemory  # noqa: F401


def base(directory: Path) -> Builder:
    return Builder().base(directory)


def java(vendor: str, version: str) -> Builder:
    return Builder().java(vendor=vendor, version=version)


def conda(environment_yaml: Path) -> Builder:
    return Builder().conda(environment_yaml=environment_yaml)


def system(directory: Path = Path(".")) -> Environment:
    return Builder().base(directory).use_system_path().build()
