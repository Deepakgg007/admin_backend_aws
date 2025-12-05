def find_two_unique_socks(arr):
    x = 0
    for v in arr:
        x ^= v

    # Get rightmost set bit of x (a ^ b)
    mask = x & -x

    a = 0
    b = 0

    for v in arr:
        if v & mask:
            a ^= v
        else:
            b ^= v

    return a, b

if __name__ == "__main__":
    n = int(input().strip())
    arr = list(map(int, input().split()))
    a, b = find_two_unique_socks(arr)
    print(a, b)