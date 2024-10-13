from richapi.exc_tracker import find_explicit_exceptions


class AnotherException(Exception): ...


class HeheException(Exception): ...


class InnerClass:
    def method(self):
        raise KeyError("An error in class method")


class WrappedException(Exception): ...


def sample_function():
    raise Exception("This is easy")

    try:
        x = 1 / 0

    except ZeroDivisionError:
        raise ValueError("Cannot divide by zero")

    try:
        raise HeheException
    except WrappedException as foo_err:
        raise foo_err

    obj = InnerClass()
    obj.method()
    err = "Haha"
    err = CustomException
    raise err
    err = "Haha"

    def nested_function():
        raise OSError("An error in nested function")


class CustomException(Exception):
    pass


exception_types = find_explicit_exceptions(sample_function)
exc_types = {exc[0] for exc in exception_types}
print(exc_types)
assert Exception in exc_types
assert CustomException in exc_types
assert ValueError in exc_types
assert OSError in exc_types
assert HeheException in exc_types
assert KeyError in exc_types
assert WrappedException in exc_types
