from lib.bot import MyBot

# class Launcher:
#     def __init__(self, token: str):
#         self.session = MyBot(token)
#         self.session.run()

if __name__ == '__main__':
    tokens = open('./data/tokens/discord', 'r', encoding='utf-8')
    token = tokens.read().split('\n')[0]
    session = MyBot(token)
    session.run()