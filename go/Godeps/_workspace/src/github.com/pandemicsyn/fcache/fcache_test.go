package fcache

import (
	"runtime"
	"sync"
	"testing"
	"time"
)

func TestFCache(t *testing.T) {
	var err error

	testcache := New(100)
	v, found := testcache.Get("wat")
	if found {
		t.Error("Cache returned found for value that shouldn't exist")
	}
	if v != nil {
		t.Error("Cache returned value that shouldn't exist")
	}

	testcache.Set("testkey", "testvalue", NoExpiration)
	v, found = testcache.Get("testkey")
	if !found || v != "testvalue" {
		t.Error("Set key doesn't exist or has incorrect value:", v)
	}

	//test expiration
	testcache.Set("expiredkey", "expiredvalue", 1*time.Nanosecond)
	time.Sleep(2 * time.Nanosecond)
	_, found = testcache.Get("expiredkey")
	if found {
		t.Error("Error encountered expired key!")
	}

	err = testcache.IncrementInt("firstpost!", 41)
	if err != nil {
		t.Error("Error while incrementing int from 0:", err)
	}
	v, found = testcache.Get("firstpost!")
	if !found {
		t.Error("Error incrementint key not found!")
	}
	if v != 41 {
		t.Error("Error incrementint value not 41:", v)
	}
	err = testcache.IncrementInt("firstpost!", 1)
	if err != nil {
		t.Error("Error while incrementing int:", err)
	}
	v, found = testcache.Get("firstpost!")
	if !found {
		t.Error("Error incrementint key not found!")
	}
	if v != 42 {
		t.Error("Error incrementint value not 42:", v)
	}

	testcache.Delete("firstpost!")
	_, found = testcache.Get("firstpost!")
	if found {
		t.Error("Error deleted key found!")
	}

	testcache.Set("something", "something", 30*time.Second)
	testcache.Empty()
	_, found = testcache.Get("something")
	if found {
		t.Error("Error flushing all keys!")
	}

}

func BenchmarkFCacheGet(b *testing.B) {
	b.StopTimer()
	c := New(100)
	c.Set("testkey", "testvalue", NoExpiration)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Get("testkey")
	}
}

func BenchmarkFCachSetGetExpired(b *testing.B) {
	b.StopTimer()
	c := New(100)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set("testkey", "testvalue", 1*time.Nanosecond)
		time.Sleep(1 * time.Nanosecond)
		c.Get("testkey")
	}
}

func BenchmarkFCacheConcurrentGet(b *testing.B) {
	b.StopTimer()
	c := New(100)
	c.Set("testkey", "testvalue", NoExpiration)
	wg := new(sync.WaitGroup)
	workers := runtime.NumCPU()
	each := b.N / workers
	wg.Add(workers)
	b.StartTimer()
	for i := 0; i < workers; i++ {
		go func() {
			for j := 0; j < each; j++ {
				c.Get("testkey")
			}
			wg.Done()
		}()
	}
	wg.Wait()
}

func BenchmarkFCacheIncrementInt(b *testing.B) {
	b.StopTimer()
	c := New(100)
	c.IncrementInt("testkey", 1)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.IncrementInt("testkey", 1)
	}
}

func BenchmarkFCacheIncrementFloat64(b *testing.B) {
	b.StopTimer()
	c := New(100)
	c.IncrementFloat64("testkey", 1.0)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.IncrementFloat64("testkey", 1.0)
	}
}

func BenchmarkFCacheSet(b *testing.B) {
	b.StopTimer()
	c := New(100)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set("1", "v", NoExpiration)
	}
}

func BenchmarkFCacheSetCast(b *testing.B) {
	b.StopTimer()
	c := New(100)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set(string(1), "v", NoExpiration)
	}
}

func BenchmarkRWMutexMapSet(b *testing.B) {
	b.StopTimer()
	m := map[string]string{}
	mu := sync.RWMutex{}
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		mu.Lock()
		m["foo"] = "bar"
		mu.Unlock()
	}
}

func BenchmarkFCacheSetDelete(b *testing.B) {
	b.StopTimer()
	c := New(100)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set("testkey", "v", NoExpiration)
		c.Delete("testkey")
	}
}

func BenchmarkRWMutexMapSetDelete(b *testing.B) {
	b.StopTimer()
	m := map[string]string{}
	mu := sync.RWMutex{}
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		mu.Lock()
		m["foo"] = "bar"
		mu.Unlock()
		mu.Lock()
		delete(m, "foo")
		mu.Unlock()
	}
}

func BenchmarkFCacheConcurrentSet(b *testing.B) {
	b.StopTimer()
	c := New(100)
	wg := new(sync.WaitGroup)
	workers := runtime.NumCPU()
	each := b.N / workers
	wg.Add(workers)
	b.StartTimer()
	for i := 0; i < workers; i++ {
		go func() {
			for j := 0; j < each; j++ {
				c.Set("testkey", "testvalue", NoExpiration)
			}
			wg.Done()
		}()
	}
	wg.Wait()
}

func BenchmarkFCacheSetGrowing(b *testing.B) {
	b.StopTimer()
	c := New(1)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set(string(i), "v", NoExpiration)
	}
}

func BenchmarkFCacheSetPreAllocated(b *testing.B) {
	b.StopTimer()
	c := New(b.N)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set(string(i), "v", NoExpiration)
	}
}

func BenchmarkFCacheSetDeleteGrowing(b *testing.B) {
	b.StopTimer()
	c := New(1)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set(string(i), "v", NoExpiration)
		c.Delete(string(i))
	}
}

func BenchmarkFCacheSetDeletePreAllocated(b *testing.B) {
	b.StopTimer()
	c := New(b.N)
	b.StartTimer()
	for i := 0; i < b.N; i++ {
		c.Set(string(i), "v", NoExpiration)
		c.Delete(string(i))
	}
}
