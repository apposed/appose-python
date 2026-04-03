# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

import unittest

import appose
from appose.util import message


class MessageTest(unittest.TestCase):
    # fmt: off
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
            '"ndArray":{'
                '"appose_type":"ndarray",'
                '"dtype":"float32",'
                '"shape":[2,20,25],'
                '"shm":{'
                    '"appose_type":"shm",'
                    '"name":"SHM_NAME",'
                    '"rsize":4000'
                "}"
            "}"
        "}"
    )

    JSON_WITH_DIMS = (
        "{"
            '"ndArray":{'
                '"appose_type":"ndarray",'
                '"dtype":"float32",'
                '"shape":[2,20,25],'
                '"dims":["z","y","x"],'
                '"shm":{'
                    '"appose_type":"shm",'
                    '"name":"SHM_NAME",'
                    '"rsize":4000'
                "}"
            "}"
        "}"
    )
    # fmt: on

    STRING: str = (
        "-=[]\\;',./_+{}|:\"<>?"
        "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"
        "~!@#$%^&*()"
    )

    NUMBERS: list[int] = [1, 1, 2, 3, 5, 8]

    WORDS: list[str] = ["quick", "brown", "fox"]

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
            json_str = message.encode(data)
            self.assertIsNotNone(json_str)
            expected = self.JSON.replace("SHM_NAME", shm_name)
            self.assertEqual(expected, json_str)

    def test_encode_with_dims(self):
        with appose.NDArray("float32", [2, 20, 25], dims=["z", "y", "x"]) as ndarray:
            shm_name = ndarray.shm.name
            data = {"ndArray": ndarray}
            json_str = message.encode(data)
            expected = self.JSON_WITH_DIMS.replace("SHM_NAME", shm_name)
            self.assertEqual(expected, json_str)

    def test_decode(self):
        with appose.SharedMemory(create=True, rsize=4000) as shm:
            shm_name = shm.name
            data = message.decode(self.JSON.replace("SHM_NAME", shm_name))
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
            self.assertIsNone(ndArray.dims)

    def test_decode_with_dims(self):
        with appose.SharedMemory(create=True, rsize=4000) as shm:
            shm_name = shm.name
            data = message.decode(self.JSON_WITH_DIMS.replace("SHM_NAME", shm_name))
            ndArray = data["ndArray"]
            self.assertEqual("float32", ndArray.dtype)
            self.assertEqual([2, 20, 25], ndArray.shape)
            self.assertEqual(["z", "y", "x"], ndArray.dims)

    def test_decode_ignores_unknown_fields(self):
        """Verify backward compatibility: unknown fields are silently ignored."""
        json_str = (
            '{"ndArray":{'
            '"appose_type":"ndarray",'
            '"dtype":"uint8",'
            '"shape":[10],'
            '"future_field":"hello",'
            '"shm":{'
            '"appose_type":"shm",'
            '"name":"SHM_NAME",'
            '"rsize":10'
            "}}}"
        )
        with appose.SharedMemory(create=True, rsize=10) as shm:
            data = message.decode(json_str.replace("SHM_NAME", shm.name))
            ndArray = data["ndArray"]
            self.assertEqual("uint8", ndArray.dtype)
            self.assertEqual([10], ndArray.shape)
            self.assertIsNone(ndArray.dims)
