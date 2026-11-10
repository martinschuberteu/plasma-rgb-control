"""Driver discovery and the CLI, with the demo driver only (no hardware is touched)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import rgbdevices  # noqa: E402


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.drivers = os.path.join(self.tmp, "drivers")
        os.makedirs(self.drivers)
        shutil.copy(os.path.join(ROOT, "examples", "demo_device.py"), self.drivers)
        self.state_file = os.path.join(self.tmp, "demo.json")
        self.config = os.path.join(self.tmp, "config.json")
        with open(self.config, "w") as f:
            json.dump({"builtin_drivers": False, "driver_dirs": [self.drivers],
                       "demo": {"state_file": self.state_file}}, f)
        # Keep the real ~/.config/rgbctl/devices out of the test.
        self.env = dict(os.environ, RGBCTL_CONFIG=self.config,
                        XDG_CONFIG_HOME=os.path.join(self.tmp, "xdg"),
                        XDG_RUNTIME_DIR=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def rgbctl(self, *args):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "rgbctl.py"), *args, "--json"],
                           capture_output=True, text=True, env=self.env)
        return r.returncode, json.loads(r.stdout)

    def write_driver(self, name, text):
        with open(os.path.join(self.drivers, name), "w") as f:
            f.write(text)

    def test_discovers_folder_driver(self):
        classes, errors = rgbdevices.discover(builtin=False, folders=[self.drivers])
        self.assertEqual(list(classes), ["demo"])
        self.assertEqual(errors, {})

    def test_builtin_drivers_found(self):
        classes, errors = rgbdevices.discover(builtin=True, folders=[])
        self.assertEqual(set(classes), {"asus", "corsair", "g815", "gpro"})
        self.assertEqual(errors, {})

    def test_broken_driver_does_not_break_others(self):
        self.write_driver("broken.py", "import does_not_exist\n")
        code, out = self.rgbctl("status")
        self.assertEqual(code, 0)
        by_id = {d["id"]: d for d in out}
        self.assertEqual(by_id["demo"]["state"]["effect"], "off")
        broken = [d for d in out if d["id"].endswith("broken.py")]
        self.assertEqual(len(broken), 1)
        self.assertIn("ModuleNotFoundError", broken[0]["error"])

    def test_duplicate_id_is_an_error(self):
        self.write_driver("zz_copy.py", "from rgbctl_driver_demo_device import DemoDevice\n"
                                        "DEVICES = {'demo': DemoDevice}\n")
        _classes, errors = rgbdevices.discover(builtin=False, folders=[self.drivers])
        self.assertIn("already used", " ".join(errors.values()))

    def test_set_all_and_equivalents(self):
        code, out = self.rgbctl("set", "all", "static", "orange")
        self.assertEqual(code, 0)
        self.assertEqual(out[0]["state"], {"effect": "static", "color": "#ff8000", "note": "demo"})
        code, out = self.rgbctl("set", "all", "rainbow")   # demo maps rainbow -> color_cycle
        self.assertEqual(out[0]["state"]["effect"], "color_cycle")
        code, effects = self.rgbctl("effects")
        rainbow = next(g for g in effects if g["id"] == "rainbow")
        self.assertEqual(rainbow["devices"], {"demo": "color_cycle"})

    def add_plain_device(self):
        """A second device ("plain") that only has off and static."""
        with open(os.path.join(ROOT, "examples", "demo_device.py")) as f:
            text = f.read()
        text = text.replace('id="demo"', 'id="plain"').replace('{"demo": DemoDevice}', '{"plain": DemoDevice}')
        text = text.replace('                Effect("breathing", "Breathing", True),\n', "")
        text = text.replace('                Effect("color_cycle", "Colour cycle", False),\n', "")
        text = text.replace('equivalents={"rainbow": "color_cycle"}', "equivalents={}")
        text = text.replace('"rgbctl-demo.json"', '"rgbctl-plain.json"')
        self.write_driver("plain_device.py", text)

    def test_unknown_effect_for_all_is_an_error(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "rgbctl.py"), "set", "all", "nosucheffect"],
                           capture_output=True, text=True, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no device has an effect like", r.stderr)

    def test_skipped_device_keeps_its_state(self):
        self.add_plain_device()
        code, out = self.rgbctl("set", "all", "static", "red")
        self.assertEqual(code, 0)
        code, out = self.rgbctl("set", "all", "breathing", "blue")   # only demo has breathing
        self.assertEqual(code, 0)
        by_id = {d["id"]: d for d in out}
        self.assertEqual(by_id["demo"]["state"]["effect"], "breathing")
        self.assertEqual(by_id["plain"]["skipped"], "has no breathing")
        self.assertEqual(by_id["plain"]["state"]["effect"], "static")
        self.assertEqual(by_id["plain"]["state"]["color"], "#ff0000")

    def test_status_waits_for_the_device_lock(self):
        import fcntl
        with open(os.path.join(self.tmp, "rgbctl.lock"), "w") as lock:   # XDG_RUNTIME_DIR = tmp
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run([sys.executable, os.path.join(ROOT, "rgbctl.py"), "status"],
                               capture_output=True, env=self.env, timeout=1.5)
        code, out = self.rgbctl("status")
        self.assertEqual(code, 0)

    def test_unknown_device(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "rgbctl.py"), "set", "nope", "off"],
                           capture_output=True, text=True, env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown device", r.stderr)


if __name__ == "__main__":
    unittest.main()
