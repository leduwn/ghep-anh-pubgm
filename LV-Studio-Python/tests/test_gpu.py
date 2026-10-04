import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ocr_engine import LevelEngine
from setup_environment import torch_flavor, torch_install_command

class AutoGpuTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.engine = LevelEngine(folder.name, device='auto')
        self.torch = MagicMock()
        self.torch.cuda.is_available.return_value = True
        self.torch.cuda.get_device_name.return_value = 'Test NVIDIA'
        self.gpu, self.cpu = MagicMock(), MagicMock()
        self.factory = MagicMock(side_effect=lambda *a, **kw: self.cpu if kw['gpu'] is False else self.gpu)
        modules = patch.dict(sys.modules, {'torch': self.torch, 'easyocr': SimpleNamespace(Reader=self.factory)})
        modules.start()
        self.addCleanup(modules.stop)

    def test_selects_gpu_and_reports_name(self):
        self.engine.warm()
        self.assertEqual(self.engine.device, 'cuda')
        self.assertEqual(self.engine.device_name, 'Test NVIDIA')
        self.assertEqual(self.factory.call_args.kwargs['gpu'], 'cuda')

    def test_no_cuda_uses_cpu(self):
        self.torch.cuda.is_available.return_value = False
        self.engine.warm()
        self.assertEqual(self.engine.device, 'cpu')
        self.assertIs(self.factory.call_args.kwargs['gpu'], False)

    def test_force_cpu_never_tries_cuda(self):
        self.engine.device_preference = 'cpu'
        self.engine.warm()
        self.torch.cuda.is_available.assert_not_called()
        self.assertIs(self.engine.reader, self.cpu)

    def test_bad_driver_falls_back(self):
        self.torch.ones.side_effect = RuntimeError('unsupported architecture')
        self.engine.warm()
        self.assertIs(self.engine.reader, self.cpu)
        self.assertIsNone(self.engine.error)

    def test_gpu_model_load_failure_falls_back(self):
        self.factory.side_effect = [RuntimeError('CUDA out of memory'), self.cpu]
        self.engine.warm()
        self.assertIs(self.engine.reader, self.cpu)
        self.assertEqual(self.factory.call_count, 2)

    def test_mid_image_oom_retries_same_region_and_stays_cpu(self):
        self.engine.warm()
        self.gpu.readtext.side_effect = RuntimeError('CUDA out of memory')
        self.cpu.readtext.return_value = [('box', '7/7', .99)]
        pixels = object()
        self.assertEqual(self.engine._readtext(pixels, canvas_size=256), self.cpu.readtext.return_value)
        self.cpu.readtext.assert_called_once_with(pixels, canvas_size=256)
        self.assertEqual(self.engine.device, 'cpu')
        self.engine._readtext(pixels)
        self.assertEqual(self.gpu.readtext.call_count, 1)

    def test_cpu_error_is_not_retried_forever(self):
        self.torch.cuda.is_available.return_value = False
        self.engine.warm()
        self.cpu.readtext.side_effect = ValueError('invalid image')
        with self.assertRaises(ValueError):
            self.engine._readtext(object())
        self.assertEqual(self.factory.call_count, 1)

class InstallGpuTests(unittest.TestCase):
    def test_no_nvidia_driver_selects_cpu(self):
        with patch.dict(os.environ, {'LV_TORCH_FLAVOR': 'auto'}), patch('setup_environment.subprocess.run', side_effect=FileNotFoundError):
            self.assertEqual(torch_flavor(), 'cpu')

    def test_nvidia_selects_cuda_wheel(self):
        response = SimpleNamespace(returncode=0, stdout='NVIDIA RTX test\n')
        with patch.dict(os.environ, {'LV_TORCH_FLAVOR': 'auto'}), patch('setup_environment.subprocess.run', return_value=response):
            self.assertEqual(torch_flavor(), 'cu128')

    def test_explicit_cuda_build_on_cpu_machine(self):
        with patch.dict(os.environ, {'LV_TORCH_FLAVOR': 'cu128'}), patch('setup_environment.subprocess.run') as command:
            self.assertEqual(torch_flavor(), 'cu128')
            command.assert_not_called()

    def test_pins_cuda_flavor_to_replace_cpu_wheels(self):
        command = torch_install_command('python', 'cu128')
        self.assertIn('torch==2.7.1+cu128', command)
        self.assertIn('torchvision==0.22.1+cu128', command)
        self.assertEqual(command[-1], 'https://download.pytorch.org/whl/cu128')
