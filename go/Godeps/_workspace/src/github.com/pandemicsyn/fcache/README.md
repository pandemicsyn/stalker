fcache
======

It's a simple cache with TTL support that does what *I need*. It probably doesn't do what you need, but thats okay...


[![GoDoc](https://godoc.org/github.com/pandemicsyn/fcache?status.svg)](https://godoc.org/github.com/pandemicsyn/fcache)

benchmark
=========

Mid 2012 Macbook Pro Retina 15 - 2.3 GHz Intel Core i7 (4 cores) - 16GB Ram

```
PASS
benchmark                                  iter       time/iter   bytes alloc        allocs
---------                                  ----       ---------   -----------        ------
BenchmarkFCacheGet                     30000000     45.30 ns/op        0 B/op   0 allocs/op
BenchmarkFCachSetGetExpired             1000000   1250.00 ns/op      144 B/op   4 allocs/op
BenchmarkFCacheConcurrentGet           30000000     44.40 ns/op        0 B/op   0 allocs/op
BenchmarkFCacheIncrementInt            20000000    115.00 ns/op        8 B/op   1 allocs/op
BenchmarkFCacheIncrementFloat64         5000000    272.00 ns/op       32 B/op   2 allocs/op
BenchmarkFCacheSet                      5000000    288.00 ns/op       48 B/op   2 allocs/op
BenchmarkFCacheSetCast                  5000000    288.00 ns/op       48 B/op   2 allocs/op
BenchmarkRWMutexMapSet                 20000000     64.50 ns/op        0 B/op   0 allocs/op
BenchmarkFCacheSetDelete                5000000    368.00 ns/op       48 B/op   2 allocs/op
BenchmarkRWMutexMapSetDelete           10000000    134.00 ns/op        0 B/op   0 allocs/op
BenchmarkFCacheConcurrentSet            5000000    321.00 ns/op       48 B/op   2 allocs/op
BenchmarkFCacheSetGrowing               1000000   1088.00 ns/op      173 B/op   3 allocs/op
BenchmarkFCacheSetPreAllocated          5000000    378.00 ns/op       52 B/op   3 allocs/op
BenchmarkFCacheSetDeleteGrowing         1000000   1088.00 ns/op       56 B/op   4 allocs/op
BenchmarkFCacheSetDeletePreAllocated    3000000    432.00 ns/op       56 B/op   4 allocs/op
ok      github.com/pandemicsyn/fcache   25.409s
```

supporting cast
===============
Inspired by go-cache and others (that extra stuff or where missing bits I wanted)
