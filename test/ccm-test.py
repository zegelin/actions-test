import argparse
import contextlib
import logging
import os
import tempfile
from pathlib import Path

from ccm_extensions import ExtendedCluster, CqlSchema
from ccmlib import extension

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def cluster_directory(path):
    path = Path(path)

    if path.exists():
        if not path.is_dir():
            raise argparse.ArgumentTypeError(f'"{path}" must be a directory.')

        if next(path.iterdir(), None) is not None:
            raise argparse.ArgumentTypeError(f'"{path}" must be an empty directory.')

    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cassandra_version', type=str, help="version of Cassandra to run", metavar="CASSANDRA_VERSION")

    parser.add_argument('--cluster-directory', type=cluster_directory, help="location to install Cassandra. Must be empty or not exist. (default is a temporary directory)")
    parser.add_argument('--keep-cluster-directory', type=bool, help="don't delete the cluster directory on exit")
    parser.add_argument('--keep-cluster-running', type=bool, help="don't stop the cluster on exit (implies --keep-cluster-directory)")

    parser.add_argument('-s', '--schema', type=CqlSchema.ArgType, help="CQL schema to apply (default: %(default)s)", default=str(CqlSchema.default_schema_path()))

    args = parser.parse_args()

    if args.cluster_directory is None:
        args.cluster_directory = Path(tempfile.mkdtemp()) / "test-cluster"
        logger.info('Cluster directory is: %s', args.cluster_directory)

    with contextlib.ExitStack() as defer:
        logger.info('Setting up Cassandra cluster.')

        ccm_cluster = ExtendedCluster(
            cluster_directory=args.cluster_directory,
            cassandra_version=args.cassandra_version,
            topology={"dc1": {"dc1-rack-a": 1, "dc1-rack-b": 1, "dc1-rack-c": 1}, "dc2": {"dc2-rack-a": 1, "dc2-rack-b": 1, "dc2-rack-c": 1}},
            # topology={"dc1": {"dc1-rack-a": 1}},
            delete_cluster_on_stop=not args.keep_cluster_directory,

        )

        if not args.keep_cluster_running:
            defer.push(ccm_cluster)

        with Path(args.cluster_directory / 'cassandra.in.sh').open('w') as f:
            # f.write('JVM_OPTS="$JVM_OPTS -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005"\n')
            f.write('CLASSPATH="$CLASSPATH:/Users/adam/Projects/ICEverywhereStrategy/target/everywhere-strategy-1.0-SNAPSHOT.jar"\n')

        # node = ccm_cluster.nodelist()[0]
        #
        # launch_bin = node.get_launch_bin()
        # args = [launch_bin, '-f']
        # env = node.get_env()
        #
        # extension.append_to_server_env(node, env)
        #
        # os.execve(launch_bin, args, env)

        logger.info('Starting cluster.')
        ccm_cluster.start()

        logger.info('Applying CQL schema.')
        ccm_cluster.apply_schema(args.schema)


        # sigh...
        node = ccm_cluster.nodelist()[0]
        env = {}
        extension.append_to_server_env(node, env)
        [node.set_environment_variable(*e) for e in env.items()]

        print(node.nodetool('status -- example').stdout)
        print(ccm_cluster.nodelist()[0].nodetool('describering -- example').stdout)
