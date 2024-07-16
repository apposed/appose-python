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
        '"words":["quick","brown","fox"]'
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
        json_str = appose.types.encode(data)
        self.assertIsNotNone(json_str)
        self.assertEqual(self.JSON, json_str)

    def test_decode(self):
        data = appose.types.decode(self.JSON)
        self.assertIsNotNone(data)
        self.assertEqual(18, len(data))
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
