# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

import numbers
import unittest
from typing import ClassVar

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
    # fmt: on

    STRING: str = (
        "-=[]\\;',./_+{}|:\"<>?"
        "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz"
        "~!@#$%^&*()"
    )

    NUMBERS: ClassVar[list[int]] = [1, 1, 2, 3, 5, 8]

    WORDS: ClassVar[list[str]] = ["quick", "brown", "fox"]

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

    def test_encode_numpy_scalars(self):
        import numpy

        data = {"f": numpy.float32(2.5), "i": numpy.int64(3), "b": numpy.bool_(True)}
        self.assertEqual('{"f":2.5,"i":3,"b":true}', message.encode(data))

    def test_encode_registered_scalars(self):
        class Scalar:
            def __init__(self, value):
                self.value = value

            def __int__(self):
                return int(self.value)

            def __float__(self):
                return float(self.value)

        class IntScalar(Scalar):
            pass

        numbers.Integral.register(IntScalar)
        numbers.Real.register(Scalar)

        data = {"f": Scalar(2.5), "i": IntScalar(3)}
        self.assertEqual('{"f":2.5,"i":3}', message.encode(data))

    def test_encode_complex_unsupported(self):
        import numpy

        # A complex number is not real, so it is not encoded as a number.
        with self.assertRaises(TypeError):
            message.encode({"c": numpy.complex64(1 + 2j)})

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
