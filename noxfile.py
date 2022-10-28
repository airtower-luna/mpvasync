import nox


@nox.session
def lint(session):
    """Lint using Flake8."""
    session.install('flake8')
    session.run('flake8', '--statistics', '.')


@nox.session
def typecheck(session):
    """Typecheck using MyPy."""
    session.install('mypy')
    session.run('mypy', '.')


@nox.session(python=['3.9', '3.10', '3.11'])
def test(session):
    """Run tests, report coverage."""
    session.install('.[tests]')
    session.run('coverage', 'run', '--parallel-mode', '-m', 'unittest', '-v')


@nox.session
def coverage(session):
    """Generage coverage report."""
    session.install('coverage')
    session.run('coverage', 'combine')
    session.run('coverage', 'report', '-m', 'mpvasync.py')
    session.run('coverage', 'html', 'mpvasync.py')
