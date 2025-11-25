# Function to find leaders in the array
def find_leaders(arr, n):
    leaders = []
    max_from_right = -10**18  # small sentinel
    # traverse from right to left
    for i in range(n-1, -1, -1):
        if arr[i] >= max_from_right:
            leaders.append(arr[i])
            max_from_right = arr[i]
    leaders.reverse()  # restore original order
    return leaders

# Main driver code
if __name__ == "__main__":
    n = int(input().strip())
    arr = list(map(int, input().split()))

    leaders = find_leaders(arr, n)
    print(" ".join(map(str, leaders)))