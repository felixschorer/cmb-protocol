## Request Resource
Packet which is sent to establish a connection.
Each connection is tied to a resource which should be transferred in this connection.
The connection is torn down at sender and receiver once the resource has been transferred.
Bounded exponential back-off is used to resend the packet in case it got dropped. 
```
     0                              15 16                             32
    ┌─────────────────────────────────┬────────────────┬────────────────┐
  0 |              0xcb00             |     Flags      |    Reserved    |
    ├─────────────────────────────────┴────────────────┴────────────────┤
  4 |                                                                   |
    |                                                                   |
  8 |                                                                   |
    |                            Resource ID                            |
 12 |                                                                   |
    |                                                                   |
 16 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 20 |                                                                   |
    |                            Block Offset                           |
 24 |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Flags: 8 bit field for specifying various options
  - 0x01 REVERSE: Reverse the order in which the blocks are sent
- Resource ID: 128 bit identifier of the requested resource
- Block Offset: 64 bit unsigned integer to resume the transfer from a previous connection

## Data With Metadata
Packets which are sent in response to a Resource Request packet.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb02             |            Reserved             |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 12 |                                                                   |
    ├ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ FEC Data  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ┤
  X |                                                                   | 
    ├───────────────────────────────────────────────────────────────────┤
X+4 |                                                                   |
    |                           Resource Size                           |
X+8 |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 64 bit identifier of the block this packet belongs to
- FEC Data: Data of the resource encoded using forward error correction
- Resource Size: Length of the resource in bytes (64 bit unsigned integer)

## Data
Packets which are sent once the transmission metadata has been acknowledged.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb01             |            Reserved             |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 12 |                                                                   |
    ├ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ FEC Data  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ┤
  X |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 64 bit identifier of the block this packet belongs to
- FEC Data: Data of the resource encoded using forward error correction

## Ack Block
Acknowledges the receipt of a block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb03             |            Reserved             |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 64 bit identifier of the block whose receipt has been acknowledged

## Ack Metadata
Acknowledges the receipt of transmission metadata.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb04             |            Reserved             |
    └───────────────────────────────────────────────────────────────────┘
```

## Nack Block
Packet to notify the sender to send repair packets of the given block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb05             |          Lost Packets           |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    └───────────────────────────────────────────────────────────────────┘
```
- Lost Packets: Number of packets of this block which have been lost (16 bit unsigned integer)
- Block ID: 64 bit identifier of the block whose receipt has been acknowledged