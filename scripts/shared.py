# Standard library
import logging
import os
from datetime import datetime, timezone

# Third-party
from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from pandas import PeriodIndex


class QuantifyingException(Exception):
    def __init__(self, message, exit_code=None):
        self.exit_code = exit_code if exit_code is not None else 1
        self.message = message
        super().__init__(self.message)


def git_fetch_and_merge(args, repo_path, branch=None):
    if not args.enable_git:
        return
    try:
        repo = Repo(repo_path)
        origin = repo.remote(name="origin")
        origin.fetch()

        # Determine the branch to use
        if branch is None:
            # Use the current branch if no branch is provided
            branch = repo.active_branch.name if repo.active_branch else "main"

        # Ensure that the branch exists in the remote
        if f"origin/{branch}" not in [ref.name for ref in repo.refs]:
            raise ValueError(
                f"Branch '{branch}' does not exist in remote 'origin'"
            )

        repo.git.merge(f"origin/{branch}", allow_unrelated_histories=True)
        logging.info(f"Fetched and merged latest changes from {branch}")
    except InvalidGitRepositoryError:
        raise QuantifyingException(f"Invalid Git repository at {repo_path}", 2)
    except NoSuchPathError:
        raise QuantifyingException(f"No such path: {repo_path}", 3)
    except Exception as e:
        raise QuantifyingException(f"Error during fetch and merge: {e}", 1)


def git_add_and_commit(args, repo_path, add_path, message):
    if not args.enable_git:
        return args
    try:
        repo = Repo(repo_path)
        if not repo.is_dirty(untracked_files=True, path=add_path):
            relative_add_path = os.path.relpath(add_path, repo_path)
            logging.info(f"No changes to commit in: {relative_add_path}")
            args.enable_git = False
            return args
        repo.index.add([add_path])
        repo.index.commit(message)
        logging.info(f"Changes committed: {message}")
    except InvalidGitRepositoryError:
        raise QuantifyingException(f"Invalid Git repository at {repo_path}", 2)
    except NoSuchPathError:
        raise QuantifyingException(f"No such path: {repo_path}", 3)
    except Exception as e:
        raise QuantifyingException(f"Error during add and commit: {e}", 1)
    return args


def git_push_changes(args, repo_path):
    if not args.enable_git:
        return
    try:
        repo = Repo(repo_path)
        origin = repo.remote(name="origin")
        origin.push().raise_if_error()
        logging.info("Changes pushed")
    except InvalidGitRepositoryError:
        raise QuantifyingException(f"Invalid Git repository at {repo_path}", 2)
    except NoSuchPathError:
        raise QuantifyingException(f"No such path: {repo_path}", 3)
    except Exception as e:
        raise QuantifyingException(f"Error during push changes: {e}", 1)


def path_join(*paths):
    return os.path.abspath(os.path.realpath(os.path.join(*paths)))


def paths_log(logger, paths):
    paths_list = []
    repo_path = paths["repo"]
    for label, path in paths.items():
        label = f"{label}:"
        if label == "repo:":
            paths_list.append(f"\n{' ' * 4}{label} {path}")
        else:
            path_new = path.replace(repo_path, ".")
            paths_list.append(f"\n{' ' * 8}{label:<15} {path_new}")
    paths_list = "".join(paths_list)
    logger.info(f"PATHS:{paths_list}")


def paths_update(logger, paths, old_quarter, new_quarter):
    logger.info(f"Updating paths: replacing {old_quarter} with {new_quarter}")
    for label in [
        "data_1-fetch",
        "data_2-process",
        "data_3-report",
        "data_phase",
        "data_quarter",
    ]:
        paths[label] = paths[label].replace(old_quarter, new_quarter)
    return paths


def setup(current_file):
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Datetime
    datetime_today = datetime.now(timezone.utc)
    quarter = PeriodIndex([datetime_today.date()], freq="Q")[0]

    # Paths
    paths = {}
    paths["repo"] = os.path.dirname(path_join(__file__, ".."))
    paths["dotenv"] = path_join(paths["repo"], ".env")
    paths["data"] = os.path.dirname(
        os.path.abspath(os.path.realpath(current_file))
    )
    current_phase = os.path.basename(
        os.path.dirname(os.path.abspath(os.path.realpath(current_file)))
    )
    paths["data"] = path_join(paths["repo"], "data")
    data_quarter = path_join(paths["data"], f"{quarter}")
    for phase in ["1-fetch", "2-process", "3-report"]:
        paths[f"data_{phase}"] = path_join(data_quarter, phase)
    paths["data_phase"] = path_join(data_quarter, current_phase)

    paths["data_quarter"] = data_quarter

    return logger, paths


def update_readme(
    args,
    section_title,
    entry_title,
    image_path,
    image_caption,
    entry_text=None,
):
    """
    Update the README.md file with the generated images and descriptions.
    """
    if not args.enable_save:
        return
    if image_path and not image_caption:
        raise QuantifyingException(
            "The update_readme function requires an image caption if an image"
            " path is provided"
        )
    if not image_path and image_caption:
        raise QuantifyingException(
            "The update_readme function requires an image path if an image"
            " caption is provided"
        )

    logger = args.logger
    paths = args.paths

    readme_path = path_join(paths["data"], args.quarter, "README.md")

    # Define section markers for each data source
    section_start_line = f"<!-- {section_title} Start -->\n"
    section_end_line = f"<!-- {section_title} End -->\n"

    # Define entry markers for each plot (optional) and description
    entry_start_line = f"<!-- {entry_title} Start -->\n"
    entry_end_line = f"<!-- {entry_title} End -->\n"

    if os.path.exists(readme_path):
        with open(readme_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []

    title_line = f"# Quantifying the Commons {args.quarter}\n"
    if not lines or lines[0].strip() != title_line.strip():
        # Add the title if it is not present or is incorrect
        lines.insert(0, title_line)
        lines.insert(1, "\n")

    # We only need to know the position of the end to append new entries
    if section_start_line in lines:
        # Locate the data source section if it is already present
        section_end_index = lines.index(section_end_line)
    else:
        # Add the data source section if it is absent
        lines.extend(
            [
                f"{section_start_line}",
                "\n",
                "\n",
                f"## {section_title}\n",
                "\n",
                "\n",
                f"{section_end_line}",
                "\n",
            ]
        )
        section_end_index = lines.index(section_end_line)

    # Locate the entry if it is already present
    if entry_start_line in lines:
        entry_start_index = lines.index(entry_start_line)
        entry_end_index = lines.index(entry_end_line)
        # Include any trailing empty/whitespace-only lines
        while not lines[entry_end_index + 1].strip():
            entry_end_index += 1
    # Initalize variables of entry is not present
    else:
        entry_start_index = None
        entry_end_index = None

    # Create entry markdown content
    if image_path:
        relative_image_path = os.path.relpath(
            image_path, os.path.dirname(readme_path)
        )
        image = f"\n![{image_caption}]({relative_image_path})\n"
    else:
        image = ""
    if entry_text and image_caption:
        text = f"\n{image_caption}\n\n{entry_text}\n"
    elif entry_text:
        text = f"\n{entry_text}\n"
    elif image_caption:
        text = f"\n{image_caption}\n"
    else:
        text = ""
    entry_lines = [
        f"{entry_start_line}",
        "\n",
        f"### {entry_title}\n",
        image,
        text,
        "\n",
        f"{entry_end_line}",
        "\n",
        "\n",
    ]

    if entry_start_index is None:
        # Add entry to end of section
        lines = (
            lines[:section_end_index] + entry_lines + lines[section_end_index:]
        )
    else:
        # Replace entry
        lines = (
            lines[:entry_start_index]
            + entry_lines
            + lines[entry_end_index + 1 :]  # noqa: E203
        )

    # Write back to the README.md file
    with open(readme_path, "w") as f:
        f.writelines(lines)

    logger.info(f"README path: {readme_path.replace(paths['repo'], '.')}")
    logger.info(
        f"Updated README with new image and description for {entry_title}."
    )
