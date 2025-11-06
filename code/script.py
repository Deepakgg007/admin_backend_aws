# Problem: Sum of Two Numbers
# Reads two integers and prints their sum.

def solution():
    # Read input from user (single line, space-separated integers)
    a, b = map(int, input().split())
    
    # Return their sum
    return a + b

# Test your code
if __name__ == "__main__":
    result = solution()
    print(result)