def ladderLength(beginWord, endWord, wordList):
    # TODO: Implement BFS
    return 0

if __name__=="__main__":
    beginWord=input().strip()
    endWord=input().strip()
    n=int(input())
    wordList=input().split()
    print(ladderLength(beginWord,endWord,wordList))