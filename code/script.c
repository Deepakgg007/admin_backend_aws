#include <stdio.h>

void compareTriplets(int a[3], int b[3], int result[2]) {
    // Write your code here
}

int main() {
    int a[3], b[3], result[2];

    for (int i = 0; i < 3; i++) {
        scanf("%d", &a[i]);
    }
    for (int i = 0; i < 3; i++) {
        scanf("%d", &b[i]);
    }

    compareTriplets(a, b, result);
    printf("%d %d\n", result[0], result[1]);
    return 0;
}