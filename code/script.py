def find_missing_roll(rolls, n):
    total = n*(n+1)//2
    return total - sum(rolls)

if __name__ == "__main__":
    n = int(input().strip())
    rolls = list(map(int, input().split()))
    print(find_missing_roll(rolls, n))