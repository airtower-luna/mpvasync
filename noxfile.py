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
    session.install('.[argcomplete]')
    session.run('mypy', '.')


@nox.session(python=['3.13', '3.14'])
def test(session):
    """Run tests, report coverage."""
    session.install('.[tests]')
    session.run(
        'pytest', '-vv',
        '--override-ini=pythonpath=',
        '--cov', '--cov-report=term', '--cov-context=test',
        env={'COVERAGE_FILE': f'.coverage.{session.python}'})
    session.notify('coverage')


@nox.session
def coverage(session):
    """Generate combined coverage report."""
    session.install('coverage')
    session.run('coverage', 'combine')
    session.run('coverage', 'html', '--show-contexts')
