###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2024 Appose developers.
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

import unittest

import appose


class TypesTest(unittest.TestCase):
    JSON = (
        "{"
        '"posByte":123,"negByte":-98,'
        '"posDouble":9.876543210123456,"negDouble":-1.234567890987654e+302,'
        '"posFloat":9.876543,"negFloat":-1.2345678,'
        '"posInt":1234567890,"negInt":-987654321,'
        '"posLong":12345678987654321,"negLong":-98765432123456789,'
        '"posShort":32109,"negShort":-23456,'
        '"trueBoolean":true,"falseBoolean":false,'
        '"nullChar":"\\u0000",'
        '"aString":"-=[]\\\\;\',./_+{}|:\\"<>?'
        "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"
        '~!@#$%^&*()",'
        '"numbers":[1,1,2,3,5,8],'
        '"words":["quick","brown","fox"],'
        # fmt: off
        '"ndArray":{'
            '"appose_type":"ndarray",'  # noqa: E131
            '"dtype":"float32",'        # noqa: E131
            '"shape":[2,20,25],'        # noqa: E131
            '"shm":{'                   # noqa: E131
                '"appose_type":"shm",'  # noqa: E131
                '"name":"SHM_NAME",'    # noqa: E131
                '"size":4000'           # noqa: E131
            "}"                         # noqa: E131
        "}"
        # fmt: on
        "}"
    )

    STRING = (
        "-=[]\\;',./_+{}|:\"<>?"
        "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"
        "~!@#$%^&*()"
    )

    NUMBERS = [1, 1, 2, 3, 5, 8]

    WORDS = ["quick", "brown", "fox"]

    def test_encode(self):
        data = {
            "posByte": 123,
            "negByte": -98,
            "posDouble": 9.876543210123456,
            "negDouble": -1.234567890987654e302,
            "posFloat": 9.876543,
            "negFloat": -1.2345678,
            "posInt": 1234567890,
            "negInt": -987654321,
            "posLong": 12345678987654321,
            "negLong": -98765432123456789,
            "posShort": 32109,
            "negShort": -23456,
            "trueBoolean": True,
            "falseBoolean": False,
            "nullChar": "\0",
            "aString": self.STRING,
            "numbers": self.NUMBERS,
            "words": self.WORDS,
        }
        with appose.NDArray("float32", [2, 20, 25]) as ndarray:
            shm_name = ndarray.shm.name
            data["ndArray"] = ndarray
            json_str = appose.types.encode(data)
            self.assertIsNotNone(json_str)
            expected = self.JSON.replace("SHM_NAME", shm_name)
            self.assertEqual(expected, json_str)

    def test_decode(self):
        with appose.SharedMemory(create=True, size=4000) as shm:
            shm_name = shm.name
            data = appose.types.decode(self.JSON.replace("SHM_NAME", shm_name))
            self.assertIsNotNone(data)
            self.assertEqual(19, len(data))
            self.assertEqual(123, data["posByte"])
            self.assertEqual(-98, data["negByte"])
            self.assertEqual(9.876543210123456, data["posDouble"])
            self.assertEqual(-1.234567890987654e302, data["negDouble"])
            self.assertEqual(9.876543, data["posFloat"])
            self.assertEqual(-1.2345678, data["negFloat"])
            self.assertEqual(1234567890, data["posInt"])
            self.assertEqual(-987654321, data["negInt"])
            self.assertEqual(12345678987654321, data["posLong"])
            self.assertEqual(-98765432123456789, data["negLong"])
            self.assertEqual(32109, data["posShort"])
            self.assertEqual(-23456, data["negShort"])
            self.assertTrue(data["trueBoolean"])
            self.assertFalse(data["falseBoolean"])
            self.assertEqual("\0", data["nullChar"])
            self.assertEqual(self.STRING, data["aString"])
            self.assertEqual(self.NUMBERS, data["numbers"])
            self.assertEqual(self.WORDS, data["words"])
            ndArray = data["ndArray"]
            self.assertEqual("float32", ndArray.dtype)
            self.assertEqual([2, 20, 25], ndArray.shape)
