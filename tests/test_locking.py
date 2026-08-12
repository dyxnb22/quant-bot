import pytest

from quantlab.locking import file_lock


def test_lock_acquire_release_reacquire():
    with file_lock("test_lock", timeout=1):
        pass
    with file_lock("test_lock", timeout=1):
        pass


def test_lock_mutual_exclusion():
    with file_lock("test_lock2", timeout=1):
        with pytest.raises(TimeoutError):
            # 第二个独立文件描述符在锁持有期内必须拿不到锁
            with file_lock("test_lock2", timeout=0.1, poll=0.05):
                pass
