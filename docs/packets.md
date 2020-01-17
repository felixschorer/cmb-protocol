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
    |                          Resource Length                          |
 24 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 28 |                                                                   |
    |                            Block Offset                           |
 32 |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Flags: 8 bit field for specifying various options
  - 0x01 REVERSE: Reverse the order in which the blocks are sent
- Resource ID: 128 bit identifier of the requested resource
- Resource Length: Length of the resource
- Block Offset: 64 bit unsigned integer to resume the transfer from a previous connection

## Data
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

## Nack Block
Packet to notify the sender to send repair packets of the given block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb05             |        Received Packets         |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    └───────────────────────────────────────────────────────────────────┘
```
- Received Packets: Number of packets of this block which have been received (16 bit unsigned integer)
- Block ID: 64 bit identifier of the block whose receipt has been acknowledged

## Ack Opposite Range
Send by send_stop by the client in order to stop the sending process.
Acknowledges the receipt of a block range from the given block to the end of the block sequence.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb06             |            Reserved             |
    ├─────────────────────────────────┴─────────────────────────────────┤
  4 |                                                                   |
    |                             Block ID                              |
  8 |                                                                   |
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 64 bit identifier of the block who marks the start of the range