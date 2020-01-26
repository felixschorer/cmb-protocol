## Request Resource
Packet which is sent by the receiver to establish a connection.
Each connection is tied to a resource which should be transferred in this connection.
The connection is torn down at sender and receiver once the resource has been transferred.
After the connection has been established, the packet will be sent periodically to measure the round trip time 
and to regulate the rate at which the sender sends.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬────────────────┬────────────────┐
  0 |              0xcb00             |    Reserved    |    Timestamp   |
    ├─────────────────────────────────┼────────────────┴────────────────┤
  4 |            Timestamp            |           Sending Rate          |
    ├─────────────────────────────────┼─────────────────────────────────┤
  8 |           Sending Rate          |                                 |
    ├─────────────────────────────────┘                                 |
 12 |                         Block Range Start                         |
    ├───────────────────────────────────────────────────────────────────┤
 16 |                                                                   |
    |                                                                   |
 20 |                                                                   |
    |                           Resource Hash                           |
 24 |                                                                   |
    |                                                                   |
 28 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 32 |                                                                   |
    |                         Resource Length                           |
 36 |                                                                   |
    ├───────────────────────────────────────────────────────────────────┤
 40 |                         Block Range End                           |
    |                                 ┌─────────────────────────────────┘
 44 |                                 |
    └─────────────────────────────────┘
```
- Timestamp: 24 bit relative timestamp in milliseconds
- Sending Rate: 32 bit unsigned integer in bps 
- Block Range Start: 48 bit unsigned integer marking the start of the range (inclusive)
- Resource Hash: 128 bit identifier of the requested resource
- Resource Length: Length of the resource
- Block Range End: 48 bit unsigned integer marking the end of the range (exclusive)

## Data
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb01             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                             Block ID                              |
    ├──────────────────────────────────────────────────┬────────────────┤
  8 |                     Timestamp                    |     Delay      |
    ├────────────────┬─────────────────────────────────┴────────────────┤
 12 |     Delay      |                  Sequence Number                 |
    ├────────────────┴──────────────────────────────────────────────────┤
 14 |                                                                   |
    ├ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ FEC Data  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ┤
  X |                                                                   | 
    └───────────────────────────────────────────────────────────────────┘
```
- Block ID: 48 bit identifier of the block this packet belongs to
- Timestamp: 24 bit timestamp in milliseconds starting at 0
- Delay: 16 bit unsigned integer holding the amount of milliseconds elapsed between the receipt of the last 
  `RequstResoucre` packet at the sender and the generation of this `Data` packet.
- Sequence Number: 24 bit sequence number
- FEC Data: Data of the resource encoded using forward error correction

## Ack Block
Acknowledges the receipt of a block.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb02             |                                 |
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
  0 |              0xcb03             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                             Block ID                              |
    ├─────────────────────────────────┬─────────────────────────────────┘
  8 |        Received Packets         | 
    └─────────────────────────────────┘
```
- Block ID: 48 bit identifier of the block whose receipt has been acknowledged
- Received Packets: Number of packets of this block which have been received (16 bit unsigned integer)

## Shrink Range
Send by send_stop by the client in order to stop the sending process.
Acknowledges the receipt of a block range from the given block to the end of the block sequence.
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb04             |                                 |
    ├─────────────────────────────────┘                                 |
  4 |                        Block Range Start                          |
    ├───────────────────────────────────────────────────────────────────┤
  8 |                         Block Range End                           |
    |                                 ┌─────────────────────────────────┘
 12 |                                 |
    └─────────────────────────────────┘
```
- Block Range Start: 48 bit unsigned integer marking the start of the range (inclusive)
- Block Range End: 48 bit unsigned integer marking the end of the range (exclusive)

## Error
Generic error packet that can be identified by its Error Code
```
     0                              15 16                             32
    ┌─────────────────────────────────┬─────────────────────────────────┐
  0 |              0xcb05             |           Error Code            |
    └─────────────────────────────────┴─────────────────────────────────┘
```
- Error Code: 16 bit error code
