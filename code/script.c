#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int *data;
    int front;
    int rear;
    int size;
} Deque;

Deque* createDeque(int capacity) {
    Deque *dq = (Deque *)malloc(sizeof(Deque));
    dq->data = (int *)malloc(capacity * sizeof(int));
    dq->front = 0;
    dq->rear = -1;
    dq->size = 0;
    return dq;
}

void destroyDeque(Deque *dq) {
    free(dq->data);
    free(dq);
}

int isEmpty(Deque *dq) {
    return dq->size == 0;
}

void pushBack(Deque *dq, int val) {
    dq->rear = (dq->rear + 1);
    dq->data[dq->rear] = val;
    dq->size++;
}

void popFront(Deque *dq) {
    dq->front = (dq->front + 1);
    dq->size--;
}

void popBack(Deque *dq) {
    dq->rear--;
    dq->size--;
}

int front(Deque *dq) {
    return dq->data[dq->front];
}

int back(Deque *dq) {
    return dq->data[dq->rear];
}

void slidingWindowMaximum(int *nums, int n, int k) {
    Deque *dq = createDeque(n);
    for (int i = 0; i < n; i++) {
        // Remove elements out of this window
        if (!isEmpty(dq) && front(dq) <= i - k)
            popFront(dq);

        // Remove elements smaller than current from the back
        while (!isEmpty(dq) && nums[back(dq)] < nums[i])
            popBack(dq);

        pushBack(dq, i);

        // Output result if window is fully seen
        if (i >= k - 1)
            printf("%d ", nums[front(dq)]);
    }
    destroyDeque(dq);
}

int main() {
    int n, k;
    scanf("%d %d", &n, &k);
    int *nums = (int *)malloc(n * sizeof(int));
    for (int i = 0; i < n; i++) {
        scanf("%d", &nums[i]);
    }
    slidingWindowMaximum(nums, n, k);
    free(nums);
    return 0;
}
