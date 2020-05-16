import argparse
import contextlib
import logging
import os
import sys
import tempfile
from pathlib import Path

from ccm_extensions import ExtendedCluster, CqlSchema, ExtendedDseCluster
from ccmlib import extension

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def set_java_home():
    env = {}
    extension.append_to_server_env(None, env)

    os.environ.update(env)


set_java_home()


def add_strategy_jar(cluster_dir: Path):
    with Path(cluster_dir / 'cassandra.in.sh').open('w') as f:
        # f.write('JVM_OPTS="$JVM_OPTS -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005"\n')
        f.write('CLASSPATH="$CLASSPATH:/Users/adam/Projects/ICEverywhereStrategy/target/everywhere-strategy-1.0-SNAPSHOT.jar"\n')


def nodetool_status(cluster):
    node = cluster.nodelist()[0]
    return node.nodetool('status -- example').stdout


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cassandra_version', type=str, help="version of Cassandra to run", metavar="CASSANDRA_VERSION")
    parser.add_argument('dse_version', type=str, help="version of DSE Cassandra to run", metavar="DSE_VERSION")

    parser.add_argument('--keep-cluster-directory', type=bool, help="don't delete the cluster directory on exit")
    parser.add_argument('--keep-cluster-running', type=bool, help="don't stop the cluster on exit (implies --keep-cluster-directory)")

    parser.add_argument('-s', '--schema', type=CqlSchema.ArgType, help="CQL schema to apply (default: %(default)s)", default=str(CqlSchema.default_schema_path()))

    args = parser.parse_args()

    cluster_name = 'test-cluster'

    base_dir = Path(tempfile.mkdtemp())

    cassandra_directory = base_dir / 'cassandra' / cluster_name
    dse_directory = base_dir / 'dse' / cluster_name
    logger.info('Cassandra directory is: %s', cassandra_directory)
    logger.info('DSE directory is: %s', dse_directory)

    os.makedirs(cassandra_directory)
    os.makedirs(dse_directory)

    with contextlib.ExitStack() as defer:
        logger.info('Setting up DSE cluster.')
        dse_cluster = ExtendedDseCluster(
            cluster_directory=dse_directory,
            cassandra_version=args.dse_version,
            topology={"dse_dc": {"dse_dc-rack-a": 1, "dse_dc-rack-b": 1, "dse_dc-rack-c": 1}},
            delete_cluster_on_stop=not args.keep_cluster_directory
        )

        if not args.keep_cluster_running:
            defer.push(dse_cluster)

        # needed for DSE 6.8
        # for node in dse_cluster.nodelist():
        #     node.set_configuration_options({'metadata_directory': node.get_path()})

        logger.info('Starting DSE cluster.')
        dse_cluster.start()

        logger.info('Applying CQL schema.')
        dse_cluster.apply_schema(args.schema)

        logger.info('DSE nodetool status:\n' + nodetool_status(dse_cluster))


        logger.info('Setting up Cassandra cluster.')

        class CassandraCluster(ExtendedCluster):
            def create_node(self, jmx_port, remote_debug_port, *args, **kwargs):
                return super().create_node(*args,
                                    jmx_port=str(int(jmx_port)+1000),  # why is this a string??? why?!?
                                    remote_debug_port='0' if remote_debug_port == '0' else str(int(remote_debug_port)+1000),  # why is this a string??? why?!?
                                    **kwargs)

            def get_seeds(self):
                return [n.network_interfaces['storage'][0] for n in dse_cluster.nodelist()]

        cassandra_cluster = CassandraCluster(
            cluster_directory=cassandra_directory,
            cassandra_version=args.cassandra_version,
            topology={"cassandra_dc": {"cassandra_dc-rack-a": 1, "cassandra_dc-rack-b": 1, "cassandra_dc-rack-c": 1}},
            # topology={"cassandra_dc": {"cassandra_dc-rack-a": 1}},
            ipformat='127.0.1.%d'
        )

        if not args.keep_cluster_running:
            defer.push(cassandra_cluster)

        add_strategy_jar(cassandra_directory)

        logger.info('Starting Cassandra cluster.')
        cassandra_cluster.start()

        for node in cassandra_cluster.nodelist():
            node.nodetool('rebuild --keyspace example -- dse_dc')
            node.nodetool('rebuild --keyspace dse_system -- dse_dc')

        logger.info('Cassandra nodetool status:\n' + nodetool_status(cassandra_cluster))


