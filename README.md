Howto:

    # Import the module
    from devantech_relays import eth

    # Initiate a relay instance
    relay = eth.ETHRelay('10.10.10.10', password='password')

    # Set relay 1 to closed
    relay.set_relay_state(1, True)

    # Check if relay 1 is closed
    relay.get_relay_state(1)
