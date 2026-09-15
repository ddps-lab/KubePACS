import argparse
import unittest

from check_optimizer import check_result, parse_case


class OptimizerCheckTests(unittest.TestCase):
    def test_parse_case(self):
        self.assertEqual(parse_case("10,0.5,2"), (10, 0.5, 2))
        for value in ("0,1,2", "1.5,1,2", "10,nan,2", "10,1,inf", "10,-1,2", "10,1"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                parse_case(value)

    def test_result_checks(self):
        mapping = {"use1-az1": "us-east-1a"}
        result = {
            "actual_pods": 10, "cost": 1, "performance": 100,
            "nodepool_config": [{"instance_type": "t2.small",
                                 "availability_zone": "us-east-1a",
                                 "num_instances": 2, "T3": 5}],
        }
        check_result(result, 10, mapping)
        with self.assertRaises(ValueError):
            check_result(result, 11, mapping)
        with self.assertRaises(ValueError):
            check_result(result, 10, {"use1-az1": "us-east-1b"})
        result["nodepool_config"][0]["num_instances"] = 6
        with self.assertRaises(ValueError):
            check_result(result, 10, mapping)


if __name__ == "__main__":
    unittest.main()
