def spiralPrint(matrix):
    res = []
    m, n = len(matrix), len(matrix[0])
    
    top, bottom = 0, m - 1
    left, right = 0, n - 1

    while top <= bottom and left <= right:

        # left → right
        for i in range(left, right + 1):
            res.append(matrix[top][i])
        top += 1

        # top → bottom
        for i in range(top, bottom + 1):
            res.append(matrix[i][right])
        right -= 1

        if top <= bottom:
            # right → left
            for i in range(right, left - 1, -1):
                res.append(matrix[bottom][i])
            bottom -= 1

        if left <= right:
            # bottom → top
            for i in range(bottom, top - 1, -1):
                res.append(matrix[i][left])
            left += 1

    return res


if __name__=="__main__":
    m,n=map(int,input().split())
    matrix=[list(map(int,input().split())) for _ in range(m)]
    print(*spiralPrint(matrix))