class S:

    t = {}

    @property
    def s(self):
        return self.t
    
    @s.setter
    def s(self, d: dict):
        print(d)
        self.t+d


c = S()

c.s |= {'b': 3}
print(c.s)
print({'s': 1}|{'b': 3})