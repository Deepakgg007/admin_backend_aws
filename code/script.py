def kth_smallest(times, k):
    times.sort()
    return times[k-1]
n = int(input().strip())
times = list(map(int, input().split()))
k = int(input().strip())
print(kth_smallest(times, k))