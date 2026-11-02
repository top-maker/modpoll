# Contributing to `Modpoll`

Contributions are welcome and greatly appreciated! Every little bit helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs at [https://github.com/top-maker/modpoll/issues](https://github.com/top-maker/modpoll/issues).

When reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help wanted" is open for anyone to fix.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement" and "help wanted" is open for anyone to implement.

### Write Documentation

`modpoll` could always use more documentation, whether as part of the official docs, in docstrings, or even on the web in blog posts, articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at [https://github.com/top-maker/modpoll/issues](https://github.com/top-maker/modpoll/issues).

If you are proposing a new feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible to make it easier to implement.
- Remember that this is a volunteer-driven project, and contributions are welcome.

## Get Started!

Ready to contribute? Here's how to set up `modpoll` for local development.

Install Git and uv. `main` maintains the stable CSV release; select `v2` for WoT TM/TD work.

1. Fork the `modpoll` repo on GitHub, and then clone your fork locally,

    ```bash
    git clone --branch v2 https://github.com/your-username/modpoll.git
    cd modpoll
    ```

2. Install and activate the dev environment,

    ```bash
    make install
    ```

3. Create a branch for local development,

    ```bash
    git checkout -b your-branch-name
    ```

    Now you can make your changes locally.

4. Don't forget to add test cases for your added functionality in the `tests` directory.

5. When you're done making changes, check that your changes pass the formatting tests,

    ```bash
    make check
    ```

    Then, validate that all unit tests are passing:

    ```bash
    uv run pytest tests -m "not integration"
    uv run python tools/test-wot-source.py -m "not integration"
    ```

6. Commit your changes and push your branch to GitHub:

    ```bash
    git add .
    git commit -m "Your detailed description of your changes."
    git push origin your-branch-name
    ```

    Please note this project follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification for git commits. Some of our CI/CD pipelines rely on such convention, for example, your commit message starting with `feat:` might bump the `MINOR` version.

7. Submit a pull request against the appropriate version branch. See
   [validation](docs/validation.rst) for isolated integration tests and
   [release process](docs/release-process.rst) for preview publishing.

Happy Coding!
