package org.apache.cassandra.locator;

import org.apache.cassandra.dht.Token;
import org.apache.cassandra.exceptions.ConfigurationException;

import java.lang.reflect.Field;
import java.net.InetAddress;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/*
    The strategy should be DC-aware, but DC-awareness is hardcoded to NTS throughout Cassandra.
    Hence why this implementation subclasses NTS.
 */
public class EverywhereStrategy extends NetworkTopologyStrategy {
    protected final Map<String, Integer> datacenters;

    public EverywhereStrategy(final String keyspaceName, final TokenMetadata tokenMetadata, final IEndpointSnitch snitch, final Map<String, String> configOptions) {
        super(keyspaceName, tokenMetadata, snitch, new HashMap<>(configOptions));

        try {
            // yuck. but then again, why is this private?
            // also, sucks that its final *and* and unmodifiable collection.
            // lets fix that...
            final Field field = NetworkTopologyStrategy.class.getDeclaredField("datacenters");
            field.setAccessible(true);

            this.datacenters = new HashMap<>();

            field.set(this, this.datacenters);

        } catch (final NoSuchFieldException | IllegalAccessException e) {
            throw new ConfigurationException("Failed to get datacenters field.", e);
        }
    }

    // this gets called whenever the ring topology changes.
    // redetermine the RF for each DC.
    public List<InetAddress> calculateNaturalEndpoints(final Token token, final TokenMetadata tokenMetadata) {
        final Set<InetAddress> endpoints = tokenMetadata.getAllEndpoints();

        this.configOptions.clear();

        for (final InetAddress endpoint : endpoints) {
            final String datacenter = this.snitch.getDatacenter(endpoint);
            final Integer newRF = this.datacenters.merge(datacenter, 1, Integer::sum);

            this.configOptions.put(datacenter, newRF.toString());
        }

        return super.calculateNaturalEndpoints(token, tokenMetadata);
    }
}
