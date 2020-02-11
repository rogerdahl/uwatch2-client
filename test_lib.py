import datetime
import logging

import pytz

import pytest
import uwatch2lib


class TestUwatch2Lib(object):
    @pytest.fixture()
    def client(self):
        with uwatch2lib.Uwatch2(debug=True) as u:
            yield u

    def test_set_and_get_steps_goal(self, client):
        client.set_steps_goal(3000)
        assert client.get_steps_goal() == 3000
        client.set_steps_goal(4000)
        assert client.get_steps_goal() == 4000

    def test_send_notification(self, client):
        client.send_notification("Test msg: ABC xyz 0123456789 !@#$%^&*() ฉัน䦹䦺aäæⱥàâã")

    @pytest.mark.parametrize("height", [150, 200])
    @pytest.mark.parametrize("weight", [55])
    @pytest.mark.parametrize("age", [8, 65])
    @pytest.mark.parametrize("gender", [True, False])
    def test_set_and_get_user_info(self, client, height, weight, age, gender):
        client.set_user_info(height, weight, age, gender)
        new_height, new_weight, new_age, new_gender = client.get_user_info()
        assert height == new_height
        assert weight == new_weight
        assert age == new_age
        assert gender == new_gender
        # logging.info(new_height)

    @pytest.mark.parametrize("step", [66, 211])
    def test_set_step_length(self, client, step):
        client.set_step_length(step)
        # Don't know of a way to read back the step length.

    def test_get_steps_category(self, client):
        category = client.get_steps_category()

    @pytest.mark.parametrize("enable_bool", [False, True])
    def test_get_set_quick_view(self, client, enable_bool):
        client.set_quick_view(enable_bool)
        assert client.get_quick_view() == enable_bool

    @pytest.mark.parametrize("time_tup", [(11, 1, 9, 2), (22, 0, 7, 59), (0, 0, 0, 0)])
    def test_get_set_quick_view_enabled_period(self, client, time_tup):
        client.set_quick_view_enabled_period(*time_tup)
        new_time_tup = client.get_quick_view_enabled_period()
        assert new_time_tup == time_tup

    # Works
    # def test_shutdown(self, client):
    #     client.shutdown()

    def test_find_device(self, client):
        client.find_device()

    def test_get_all_alarms(self, client):
        alarm_tup = client.get_alarms()
        for i, alarm_dict in enumerate(alarm_tup):
            logging.info(f"Alarm {i}: {client.format_alarm(alarm_dict)}")

    def test_set_metric_system(self, client):
        client.set_metric_system(True)
        assert client.get_metric_system()
        client.set_metric_system(False)
        assert not client.get_metric_system()

    def test_sync_time_to_current(self, client):
        with uwatch2lib.Uwatch2(debug=True) as client:
            client.sync_time()

    def test_sync_time_to_current(self, client):
        now = datetime.datetime.now(tz=pytz.timezone("MST"))
        with uwatch2lib.Uwatch2(debug=True) as client:
            client.sync_time(now)

    @pytest.mark.parametrize("enable_bool", [False, True])
    def test_get_set_other_message(self, client, enable_bool):
        client.set_other_message(enable_bool)
        assert client.get_other_message() == enable_bool

    @pytest.mark.parametrize("watch_face_idx", [0, 1, 2])
    def test_get_set_watch_face_to_display(self, client, watch_face_idx):
        client.set_watch_face_to_display(watch_face_idx)
        assert client.get_watch_face_to_display() == watch_face_idx

    @pytest.mark.parametrize("enable_bool", [False, True])
    def test_get_set_breathing_light(self, client, enable_bool):
        client.set_breathing_light(enable_bool)
        assert client.get_breathing_light() == enable_bool

    @pytest.mark.parametrize("time_tup", [(11, 1, 9, 2), (22, 0, 7, 59), (0, 0, 0, 0)])
    def test_get_set_quick_view_enabled_period(self, client, time_tup):
        client.set_dnd_period(*time_tup)
        new_time_tup = client.get_dnd_period()
        assert new_time_tup == time_tup

    @pytest.mark.parametrize("enable_bool", [False, True])
    def test_get_set_sedentary_reminder(self, client, enable_bool):
        client.set_sedentary_reminder(enable_bool)
        assert client.get_sedentary_reminder() == enable_bool

    @pytest.mark.parametrize("time_tup", [(11, 1, 9, 2), (22, 0, 7, 59), (0, 0, 0, 0)])
    def test_get_set_sedentary_reminder_period(self, client, time_tup):
        client.set_sedentary_reminder_period(*time_tup)
        new_time_tup = client.get_sedentary_reminder_period()
        assert new_time_tup == time_tup

    @pytest.mark.parametrize("unknown", [10, 11, 12])
    def test_get_set_timing_measure_heart_rate(self, client, unknown):
        client.set_timing_measure_heart_rate(unknown)
        assert client.get_timing_measure_heart_rate() == unknown

    def test_get_heart_rate(self, client):
        logging.info(client.get_heart_rate())
