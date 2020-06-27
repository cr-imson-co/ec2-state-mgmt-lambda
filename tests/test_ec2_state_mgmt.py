#!/usr/bin/env python
# pylint: skip-file

import unittest
from datetime import datetime
import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../src")

import ec2_state_mgmt

ec2_state_mgmt.LAMBDA.logger.disabled = True

# todo: reduce repetition throughout for filter_start_instance and filter_stop_instance tests

class MockInstance:
    def __init__(self, id, state, tags):
        self.id = id
        self.state = { 'Name': state }
        self.tags = tags


class GetInvokeTimeTestCase(unittest.TestCase):
    def test(self):
        event = datetime.fromisoformat('2020-06-26T18:30:39+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        self.assertEqual(event_hour, '18')
        self.assertEqual(event_minute, '30')

class CheckIfWeekendTestCase(unittest.TestCase):
    def test_weekend(self):
        event = datetime.fromisoformat('2020-06-27T18:30:39+00:00')
        is_weekend = ec2_state_mgmt.check_if_weekend(event)
        self.assertEqual(is_weekend, True)

    def test_weekday(self):
        event = datetime.fromisoformat('2020-06-26T18:30:39+00:00')
        is_weekend = ec2_state_mgmt.check_if_weekend(event)
        self.assertEqual(is_weekend, False)

class GetHourPhaseTestCase(unittest.TestCase):
    def test_phase_one(self):
        phase = ec2_state_mgmt.get_hour_phase('03')
        self.assertEqual(phase, ec2_state_mgmt.StateManagementPhase.PHASE_ONE)

    def test_phase_two(self):
        phase = ec2_state_mgmt.get_hour_phase('19')
        self.assertEqual(phase, ec2_state_mgmt.StateManagementPhase.PHASE_TWO)

    def test_phase_three(self):
        phase = ec2_state_mgmt.get_hour_phase('31')
        self.assertEqual(phase, ec2_state_mgmt.StateManagementPhase.PHASE_THREE)

    def test_phase_four(self):
        phase = ec2_state_mgmt.get_hour_phase('55')
        self.assertEqual(phase, ec2_state_mgmt.StateManagementPhase.PHASE_FOUR)

class CheckTagTimeFormatTestCase(unittest.TestCase):
    instance = MockInstance('i-1', 'running', [{ 'Key': 'Name', 'Value': 'test' }])

    def test_valid(self):
        self.assertIs(ec2_state_mgmt.check_tag_time_format(self.instance, 'ec2_start', '00:00'), True)

    def test_invalid(self):
        values = ['0:00', '00:0', 'A0:00', '00:A0', '25:00', '00:60']
        for value in values:
            with self.subTest(value=value):
                self.assertIs(ec2_state_mgmt.check_tag_time_format(self.instance, 'ec2_start', value), False)

class TagListToDictTestCase(unittest.TestCase):
    def test_single_entry(self):
        structure = [{
            'Key': 'Name',
            'Value': 'testname'
        }]
        self.assertEqual(ec2_state_mgmt.tag_list_to_dict(structure), {
            'Name': 'testname'
        })

    def test_multiple_entries(self):
        structure = [
            {
                'Key': 'Name',
                'Value': 'testname'
            },
            {
                'Key': 'ec2_start',
                'Value': '00:00'
            },
            {
                'Key': 'ec2_stop',
                'Value': '12:00'
            },
        ]
        self.assertEqual(ec2_state_mgmt.tag_list_to_dict(structure), {
            'Name': 'testname',
            'ec2_start': '00:00',
            'ec2_stop': '12:00'
        })

class CheckConfiguredTimeTestCase(unittest.TestCase):
    instance = MockInstance('i-1', 'running', [{ 'Key': 'Name', 'Value': 'test' }])

    def test_phase_one(self):
        values = ['00', '09', '14']
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(ec2_state_mgmt.check_configured_time(self.instance, 'ec2_start', value), '00')

    def test_phase_two(self):
        values = ['15', '22', '29']
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(ec2_state_mgmt.check_configured_time(self.instance, 'ec2_start', value), '15')

    def test_phase_one(self):
        values = ['30', '38', '44']
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(ec2_state_mgmt.check_configured_time(self.instance, 'ec2_start', value), '30')

    def test_phase_one(self):
        values = ['45', '50', '59']
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(ec2_state_mgmt.check_configured_time(self.instance, 'ec2_start', value), '45')

class FilterStartInstancesTestCase(unittest.TestCase):
    def test_nominal_start(self):
        event = datetime.fromisoformat('2020-06-26T07:13:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_already_running_instance(self):
        event = datetime.fromisoformat('2020-06-26T07:13:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesWeekendTestCase(unittest.TestCase):
    def test_weekend_prevent_start(self):
        event = datetime.fromisoformat('2020-06-27T07:13:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

    def test_weekend_allowed_start(self):
        event = datetime.fromisoformat('2020-06-27T07:13:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' },
                { 'Key': 'ec2_start_on_weekends', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

class FilterStartInstancesScheduledTestCase(unittest.TestCase):
    def test_scheduled_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T06:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_scheduled_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T06:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesScheduledOnTestCase(unittest.TestCase):
    def test_scheduled_on_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T06:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled_on', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_scheduled_on_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T06:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled_on', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesAutoOnTestCase(unittest.TestCase):
    def test_auto_on_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T05:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'auto_on', 'Value': '05' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_auto_on_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T06:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'auto_on', 'Value': '05' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesPhaseOneTestCase(unittest.TestCase):
    def test_ec2_start_phase_one_nominal(self):
        event = datetime.fromisoformat('2020-06-26T07:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_ec2_start_phase_one_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T08:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

    def test_ec2_start_phase_one_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T07:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesPhaseTwoTestCase(unittest.TestCase):
    def test_ec2_start_phase_two_nominal(self):
        event = datetime.fromisoformat('2020-06-26T07:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_ec2_start_phase_two_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T08:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

    def test_ec2_start_phase_two_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T07:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesPhaseThreeTestCase(unittest.TestCase):
    def test_ec2_start_phase_three_nominal(self):
        event = datetime.fromisoformat('2020-06-26T07:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_ec2_start_phase_three_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T08:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

    def test_ec2_start_phase_three_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T07:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStartInstancesPhaseFourTestCase(unittest.TestCase):
    def test_ec2_start_phase_four_nominal(self):
        event = datetime.fromisoformat('2020-06-26T07:46:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), True)

    def test_ec2_start_phase_four_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T08:46:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

    def test_ec2_start_phase_four_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T07:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)
        is_weekend = ec2_state_mgmt.check_if_weekend(event)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_start_instances(instance, event_hour, phase, is_weekend), False)

class FilterStopInstancesTestCase(unittest.TestCase):
    def test_nominal_stop(self):
        event = datetime.fromisoformat('2020-06-26T16:48:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' },
                { 'Key': 'ec2_stop', 'Value': '16:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_already_stopped_instance(self):
        event = datetime.fromisoformat('2020-06-26T16:48:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'stopped',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_start', 'Value': '07:00' },
                { 'Key': 'ec2_stop', 'Value': '16:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesScheduledTestCase(unittest.TestCase):
    def test_scheduled_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T18:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_scheduled_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T18:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesScheduledOffTestCase(unittest.TestCase):
    def test_scheduled_off_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T18:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled_off', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_scheduled_off_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T18:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'scheduled_off', 'Value': 'true' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesAutoOffTestCase(unittest.TestCase):
    def test_auto_off_tag_nominal(self):
        event = datetime.fromisoformat('2020-06-26T17:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'auto_off', 'Value': '17' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_auto_off_tag_miss(self):
        event = datetime.fromisoformat('2020-06-26T16:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'auto_off', 'Value': '17' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesPhaseOneTestCase(unittest.TestCase):
    def test_ec2_start_phase_one_nominal(self):
        event = datetime.fromisoformat('2020-06-26T16:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_ec2_start_phase_one_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T15:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

    def test_ec2_start_phase_one_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T16:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:00' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesPhaseTwoTestCase(unittest.TestCase):
    def test_ec2_start_phase_two_nominal(self):
        event = datetime.fromisoformat('2020-06-26T16:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_ec2_start_phase_two_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T15:16:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

    def test_ec2_start_phase_two_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T16:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:15' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesPhaseThreeTestCase(unittest.TestCase):
    def test_ec2_start_phase_three_nominal(self):
        event = datetime.fromisoformat('2020-06-26T16:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_ec2_start_phase_three_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T15:31:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

    def test_ec2_start_phase_three_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T16:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:30' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

class FilterStopInstancesPhaseFourTestCase(unittest.TestCase):
    def test_ec2_start_phase_four_nominal(self):
        event = datetime.fromisoformat('2020-06-26T16:46:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), True)

    def test_ec2_start_phase_four_miss_hour(self):
        event = datetime.fromisoformat('2020-06-26T15:46:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)

    def test_ec2_start_phase_four_miss_minute(self):
        event = datetime.fromisoformat('2020-06-26T16:01:00+00:00')
        event_hour, event_minute = ec2_state_mgmt.get_invoke_time(event)
        phase = ec2_state_mgmt.get_hour_phase(event_minute)

        instance = MockInstance(
            'i-1',
            'running',
            [
                { 'Key': 'Name', 'Value': 'test' },
                { 'Key': 'ec2_stop', 'Value': '16:45' }
            ]
        )

        self.assertIs(ec2_state_mgmt._filter_stop_instances(instance, event_hour, phase), False)


if __name__ == '__main__':
    unittest.main()
