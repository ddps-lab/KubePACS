import argparse
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_optimizer
from check_optimizer import check_result, parse_case


class OptimizerCheckTests(unittest.TestCase):
    def test_parse_case(self):
        self.assertEqual(parse_case("us-east-1,10,0.5,2"), ("us-east-1", 10, 0.5, 2))
        for value in ("0,1,2", "1.5,1,2", "10,nan,2", "10,1,inf", "10,-1,2", "10,1"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                parse_case("us-east-1," + value)
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_case("invalid-region,10,1,2")

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

    def test_recompute_capacity_cost_and_membership(self):
        mapping = {"use1-az1": "us-east-1a"}
        candidates = {("t2.small", "use1-az1"):
                      {"vCPU": "2", "Memory": "4", "SpotPrice": "0.1", "T3": "5"}}
        result = {
            "actual_pods": 4, "cost": 0.2, "performance": 100,
            "nodepool_config": [{"instance_type": "t2.small",
                                 "availability_zone": "us-east-1a",
                                 "num_instances": 2, "T3": 5}],
        }
        check_result(result, 4, mapping, candidates, 1, 2)
        for key, value in (("cost", 0.3), ("actual_pods", 5)):
            bad = copy.deepcopy(result)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_result(bad, 4, mapping, candidates, 1, 2)
        with self.assertRaises(KeyError):
            check_result(result, 4, mapping, {}, 1, 2)
        bad = copy.deepcopy(result)
        bad["nodepool_config"] *= 2
        with self.assertRaises(ValueError):
            check_result(bad, 4, mapping, candidates, 1, 2)

    def test_missing_local_input_fails_before_solver(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(check_optimizer, "DATA", Path(directory)):
                with self.assertRaises(SystemExit) as error:
                    check_optimizer.main(["--case", "us-west-2,10,1,2"])
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
