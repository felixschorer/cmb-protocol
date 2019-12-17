import struct
from enum import Enum

class Greeting(Enum):
    HELLO = 0
    HEY = 1
    GREETINGS = 2
    HOWDY = 3


_greeting_str = {
    Greeting.HELLO: 'Hello',
    Greeting.HEY: 'Hey',
    Greeting.GREETINGS: 'Greetings',
    Greeting.HOWDY: 'Howdy'
}


class Subject(Enum):
    WORLD = 0
    THERE = 1
    EVERYONE = 2


_subject_str = {
    Subject.WORLD: 'world',
    Subject.THERE: 'there',
    Subject.EVERYONE: 'everyone'
}


class Hello:
    format = '!HH'

    def __init__(self, greeting=None, subject=None):
        self.greeting = greeting
        self.subject = subject

    def to_bytes(self):
        return struct.pack(Hello.format, self.greeting.value, self.subject.value)

    def __str__(self):
        return '{}, {}!'.format(_greeting_str[self.greeting], _subject_str[self.subject])

    @staticmethod
    def from_bytes(data):
        greeting, subject = struct.unpack(Hello.format, data)
        return Hello(greeting=Greeting(greeting), subject=Subject(subject))
