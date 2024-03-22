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


@nox.session(python=['3.11'])
def test(session):
    """Run tests, report coverage."""
    session.install('.[tests]')
    session.run(
        'pytest', '-vv',
        '--cov', '--cov-report=term',
        f'--cov-report=html:htmlcov/{session.python}')
