import alfred3 as al

import alfred3_interact as ali

exp = al.Experiment()


@exp.member
class Wait(ali.WaitingPage):
    wait_timeout = 5

    def wait_for(self):
        return False


if __name__ == "__main__":
    exp.run()
