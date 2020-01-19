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
    |                           Resource Hash                           |
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
- Resource Hash: 128 bit identifier of the requested resource
- Resource Length: Length of the resource
- Block Offset: 64 bit unsigned integer to resume the transfer from a previous connection

## Data
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb01             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                             Block ID                              |
    ├──────────────────────────────────────────────────┬────────────────┤
  8 |                     Timestamp                    | Estimated RTT  |
    ├────────────────┬─────────────────────────────────┴────────────────┤
 12 | Estimated RTT  |                  Sequence Number                 |
    ├────────────────┴──────────────────────────────────────────────────┤
 14 |                                                                   |
    ├ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ FEC Data  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ┤
  X |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 48 bit identifier of the block this packet belongs to
- Timestamp: 24 bit timestamp in milliseconds starting at 0
- Estimated RTT: 16 bit estimated round trip time
- Sequence Number: 24 bit sequence number
- FEC Data: Data of the resource encoded using forward error correction

## Ack Block
Acknowledges the receipt of a block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb03             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                             Block ID                              |
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 48 bit identifier of the block whose receipt has been acknowledged

## Nack Block
Packet to notify the sender to send repair packets of the given block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb05             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                             Block ID                              |
    ├─────────────────────────────────┬─────────────────────────────────┘
  8 |        Received Packets         | 
    └─────────────────────────────────┘
```
- Block ID: 48 bit identifier of the block whose receipt has been acknowledged
- Received Packets: Number of packets of this block which have been received (16 bit unsigned integer)

## Ack Opposite Range
Send by send_stop by the client in order to stop the sending process.
Acknowledges the receipt of a block range from the given block to the end of the block sequence.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb06             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                         Stop at Block ID                          |
    └───────────────────────────────────────────────────────────────────┘
```
- Stop at Block ID: 48 bit identifier of the block who marks the start of the acknowledged range

## TFRC Feedback
Client sends feedback for measurement
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb06             |             Delay               |
    ├─────────────────────────────────┴─────────────────────────────────|
  4 |                         ...                          |
    └───────────────────────────────────────────────────────────────────┘
```
- Delay: 16 bit for the amount of time elapsed between the receipt of the last data packet at the receiver and the generation of this feedback report


## Error
Generic error packet that can be identified by its Error Code
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb07             |           Error Code            |
    └─────────────────────────────────┴─────────────────────────────────┘
```
- Error Code: 16 bit error code
